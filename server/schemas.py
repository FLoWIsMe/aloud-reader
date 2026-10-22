"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class DocumentSummary(BaseModel):
    id: str
    title: str
    source_kind: str
    source_name: str | None = None
    created_at: str
    updated_at: str
    last_opened_at: str | None = None
    word_count: int
    char_count: int
    chunk_count: int
    position: int = 0
    finished_at: str | None = None
    voice: str | None = None


class DocumentDetail(DocumentSummary):
    blocks: list[dict[str, Any]]


class TextImport(BaseModel):
    text: str = Field(min_length=1, max_length=5_000_000)
    title: str | None = Field(default=None, max_length=300)


class UrlImport(BaseModel):
    url: str = Field(min_length=4, max_length=2048)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("http://", "https://")):
            value = "https://" + value
        return value


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    position: int | None = Field(default=None, ge=0)
    voice: str | None = Field(default=None, max_length=64)
    finished: bool | None = None


class SettingsUpdate(BaseModel):
    voice: str | None = Field(default=None, max_length=64)
    browser_voice: str | None = Field(default=None, max_length=200)
    speed: float | None = Field(default=None, ge=0.5, le=5.0)
    theme: str | None = Field(default=None, pattern="^(system|light|dark)$")
    autoscroll: bool | None = None
    text_size: str | None = Field(default=None, pattern="^(small|medium|large)$")


class ModelStatusOut(BaseModel):
    state: str
    engine: str
    progress: float
    downloaded_bytes: int
    total_bytes: int
    current_file: str
    error: str | None
    updated_at: float
