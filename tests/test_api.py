from __future__ import annotations

import io
import wave

from fastapi.testclient import TestClient


def test_health_and_welcome_document(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["tts"] == "ready"
    docs = client.get("/api/documents").json()
    assert len(docs) == 1
    assert docs[0]["title"] == "Welcome to Aloud"
    assert docs[0]["source_kind"] == "bundled"
    assert docs[0]["chunk_count"] > 5


def test_import_text_and_read_it_back(client: TestClient) -> None:
    created = client.post(
        "/api/documents/text", json={"text": "Hello there. This is a test.\n\nSecond paragraph."}
    )
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["title"].startswith("Hello there.")
    assert doc["chunk_count"] == 3
    assert [block["sentences"] for block in doc["blocks"]] == [
        ["Hello there.", "This is a test."],
        ["Second paragraph."],
    ]
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["last_opened_at"] is not None
    assert fetched["blocks"] == doc["blocks"]


def test_import_text_with_explicit_title(client: TestClient) -> None:
    doc = client.post("/api/documents/text", json={"text": "Body.", "title": "My Title"}).json()
    assert doc["title"] == "My Title"


def test_upload_markdown_file(client: TestClient) -> None:
    body = io.BytesIO(b"# Heading\n\nA sentence. Another.")
    files = {"file": ("notes.md", body, "text/markdown")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["title"] == "notes"
    assert doc["blocks"][0]["kind"] == "heading"
    assert doc["source_name"] == "notes.md"


def test_upload_empty_file_is_rejected(client: TestClient) -> None:
    files = {"file": ("blank.txt", io.BytesIO(b"  \n"), "text/plain")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 422


def test_progress_is_saved_and_clamped(client: TestClient) -> None:
    doc = client.post("/api/documents/text", json={"text": "One. Two. Three."}).json()
    updated = client.patch(f"/api/documents/{doc['id']}", json={"position": 1}).json()
    assert updated["position"] == 1
    clamped = client.patch(f"/api/documents/{doc['id']}", json={"position": 99}).json()
    assert clamped["position"] == 2
    finished = client.patch(f"/api/documents/{doc['id']}", json={"finished": True}).json()
    assert finished["finished_at"] is not None
    renamed = client.patch(f"/api/documents/{doc['id']}", json={"title": "Renamed"}).json()
    assert renamed["title"] == "Renamed"


def test_delete_document(client: TestClient) -> None:
    doc = client.post("/api/documents/text", json={"text": "Gone soon."}).json()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_audio_for_each_chunk_is_valid_wav_and_cached(client: TestClient) -> None:
    payload = {"text": "First sentence. Second sentence."}
    doc = client.post("/api/documents/text", json=payload).json()
    for index in range(doc["chunk_count"]):
        response = client.get(f"/api/documents/{doc['id']}/audio/{index}?voice=stub_high")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("audio/wav")
        with wave.open(io.BytesIO(response.content), "rb") as handle:
            assert handle.getnframes() > 0
            assert handle.getframerate() == 16000
    stats = client.get("/api/tts/cache").json()
    assert stats["bytes"] > 0
    assert client.get(f"/api/documents/{doc['id']}/audio/99").status_code == 404
    cleared = client.delete("/api/tts/cache").json()
    assert cleared["removed"] == 2
    assert cleared["bytes"] == 0


def test_voices_and_preview(client: TestClient) -> None:
    voices = client.get("/api/tts/voices").json()
    assert voices["state"] == "ready"
    assert {voice["id"] for voice in voices["voices"]} == {"stub_low", "stub_high"}
    preview = client.get("/api/tts/preview?voice=stub_low")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("audio/wav")
    custom = client.get("/api/tts/preview?voice=stub_low&text=Hi+there")
    assert custom.status_code == 200


def test_model_status_endpoint(client: TestClient) -> None:
    status = client.get("/api/tts/status").json()
    assert status["state"] == "ready"
    assert status["engine"] == "stub"
    started = client.post("/api/tts/download").json()
    assert started["state"] == "ready"


def test_settings_roundtrip(client: TestClient) -> None:
    defaults = client.get("/api/settings").json()
    assert defaults["speed"] == 1.0
    assert defaults["theme"] == "system"
    changes = {"speed": 1.75, "theme": "dark", "voice": "am_michael"}
    updated = client.put("/api/settings", json=changes).json()
    assert updated["speed"] == 1.8
    assert updated["theme"] == "dark"
    assert updated["voice"] == "am_michael"
    assert client.get("/api/settings").json() == updated
    assert client.put("/api/settings", json={"speed": 9}).status_code == 422


def test_index_page_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>Aloud" in response.text
    assert client.get("/doc/abc").status_code == 200
