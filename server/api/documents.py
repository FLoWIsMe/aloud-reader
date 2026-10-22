"""Library endpoints: import, list, open, update progress, delete, and per-sentence audio."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ..db import now_iso
from ..extract import (
    ExtractionError,
    extract_file,
    extract_html,
    extract_pasted_text,
    title_from_filename,
)
from ..schemas import DocumentDetail, DocumentSummary, DocumentUpdate, TextImport, UrlImport
from ..state import AppState, get_state
from ..tts import EngineNotReady

log = logging.getLogger("aloud.api")
router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_URL_BYTES = 20 * 1024 * 1024


def _detail(state: AppState, doc: dict[str, Any]) -> DocumentDetail:
    blocks = state.db.get_blocks(doc["id"]) or []
    return DocumentDetail(**doc, blocks=blocks)


@router.get("", response_model=list[DocumentSummary])
def list_documents(state: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    return state.db.list_documents()


@router.post("/upload", response_model=DocumentDetail, status_code=201)
async def upload_document(
    file: UploadFile = File(...), state: AppState = Depends(get_state)
) -> DocumentDetail:
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty")
    if len(data) > state.config.max_upload_bytes:
        limit = state.config.max_upload_bytes // (1024 * 1024)
        raise HTTPException(413, f"Files are limited to {limit} MB")
    filename = file.filename or "document"
    try:
        extracted = extract_file(filename, data)
        doc = state.store_document(extracted, "upload", filename, title_from_filename(filename))
    except (ExtractionError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return _detail(state, doc)


@router.post("/text", response_model=DocumentDetail, status_code=201)
def import_text(payload: TextImport, state: AppState = Depends(get_state)) -> DocumentDetail:
    try:
        extracted = extract_pasted_text(payload.text)
        doc = state.store_document(extracted, "paste", None, payload.title)
    except (ExtractionError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return _detail(state, doc)


@router.post("/url", response_model=DocumentDetail, status_code=201)
async def import_url(payload: UrlImport, state: AppState = Depends(get_state)) -> DocumentDetail:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; Aloud/0.1; +https://github.com/) "
            "AppleWebKit/537.36 (KHTML, like Gecko)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    }
    timeout = httpx.Timeout(state.config.url_fetch_timeout)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            async with client.stream("GET", payload.url, headers=headers) as response:
                if response.status_code >= 400:
                    raise HTTPException(422, f"The page returned HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_URL_BYTES:
                        raise HTTPException(413, "That page is too large to import")
                    chunks.append(chunk)
                body = b"".join(chunks)
                final_url = str(response.url)
    except httpx.HTTPError as error:
        raise HTTPException(422, f"Could not fetch that link: {error}") from error
    try:
        if "pdf" in content_type.lower() or body[:5] == b"%PDF-":
            extracted = extract_file("download.pdf", body)
        else:
            encoding = response.encoding or "utf-8"
            extracted = extract_html(body.decode(encoding, errors="replace"), url=final_url)
        doc = state.store_document(extracted, "url", final_url)
    except (ExtractionError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return _detail(state, doc)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, state: AppState = Depends(get_state)) -> DocumentDetail:
    doc = state.db.get_document(document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    stamp = now_iso()
    state.db.update_document(document_id, {"last_opened_at": stamp})
    doc["last_opened_at"] = stamp
    return _detail(state, doc)


@router.patch("/{document_id}", response_model=DocumentSummary)
def update_document(
    document_id: str, payload: DocumentUpdate, state: AppState = Depends(get_state)
) -> dict[str, Any]:
    doc = state.db.get_document(document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    fields: dict[str, Any] = {"updated_at": now_iso()}
    if payload.title is not None:
        fields["title"] = payload.title.strip()[:300]
    if payload.position is not None:
        fields["position"] = min(payload.position, max(doc["chunk_count"] - 1, 0))
    if payload.voice is not None:
        fields["voice"] = payload.voice or None
    if payload.finished is not None:
        fields["finished_at"] = now_iso() if payload.finished else None
    state.db.update_document(document_id, fields)
    return state.db.get_document(document_id) or doc


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, state: AppState = Depends(get_state)) -> None:
    if not state.db.delete_document(document_id):
        raise HTTPException(404, "Document not found")


@router.get("/{document_id}/audio/{index}")
async def chunk_audio(
    document_id: str,
    index: int,
    voice: str | None = Query(default=None, max_length=64),
    state: AppState = Depends(get_state),
) -> FileResponse:
    blocks = state.db.get_blocks(document_id)
    if blocks is None:
        raise HTTPException(404, "Document not found")
    chunks = [sentence for block in blocks for sentence in block["sentences"]]
    if index < 0 or index >= len(chunks):
        raise HTTPException(404, "No such sentence")
    try:
        path = await state.synth.render(chunks[index], voice or "")
    except EngineNotReady as error:
        raise HTTPException(503, f"Natural voices are not ready ({error})") from error
    except Exception as error:
        log.exception("Synthesis failed for chunk %s of %s", index, document_id)
        raise HTTPException(500, f"Synthesis failed: {error}") from error
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={"Cache-Control": "private, max-age=86400"},
    )
