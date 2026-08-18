# app/slices/memory/schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ─── LLM Parsing Schemas (Structured Output) ──────────────────────────────────
class ResumeChunk(BaseModel):
    category: str        # "experience" | "project" | "skill" | "education"
    title: str           # e.g. "Backend Developer @ Shopcardd"
    content: str         # The full paragraph text for this chunk


class ParsedResume(BaseModel):
    chunks: list[ResumeChunk]


# ─── API Request / Response Schemas ──────────────────────────────────────────
class AddMemoryRequest(BaseModel):
    """Used for manual entry input without uploading PDF."""
    category: str         # "experience" | "project" | "skill" | "education"
    title: str
    content: str


class MemoryCardResponse(BaseModel):
    """Represents a single memory card item returned from database."""
    id: int
    category: str
    title: Optional[str] = None
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class IngestResponse(BaseModel):
    message: str
    chunks_saved: int


class DeleteResponse(BaseModel):
    message: str


class UpdateMemoryRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
