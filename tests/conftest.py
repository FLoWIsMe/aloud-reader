from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.config import Config
from server.main import create_app


@pytest.fixture
def config(tmp_path: Path) -> Config:
    os.environ["ALOUD_DATA_DIR"] = str(tmp_path / "data")
    os.environ["ALOUD_TTS_ENGINE"] = "stub"
    os.environ["ALOUD_AUTO_DOWNLOAD"] = "0"
    os.environ["ALOUD_CACHE_MAX_MB"] = "1"
    return Config.from_env()


@pytest.fixture
def client(config: Config) -> Iterator[TestClient]:
    app = create_app(config)
    with TestClient(app) as test_client:
        yield test_client
