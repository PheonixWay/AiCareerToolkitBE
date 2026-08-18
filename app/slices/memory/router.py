# app/slices/memory/router.py
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from .schemas import (
    AddMemoryRequest,
    MemoryCardResponse,
    IngestResponse,
    DeleteResponse,
    UpdateMemoryRequest,
)
from .service import (
    ingest_pdf_service,
    add_memory_service,
    get_all_memories_service,
    delete_memory_service,
    update_memory_service,
)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.post("/ingest-pdf", response_model=IngestResponse)
def ingest_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Ingest a PDF resume:
    1. Extract text via PyMuPDF
    2. Parse into semantic chunks via LLM
    3. Generate 768-dim embeddings via Google Gemini
    4. Store chunks and vectors into PostgreSQL (pgvector)
    """
    return ingest_pdf_service(file, db)


@router.post("/add", response_model=MemoryCardResponse)
def add_memory(
    request: AddMemoryRequest,
    db: Session = Depends(get_db),
):
    """
    Add an individual memory item manually (bypasses PDF extraction and LLM parsing).
    Directly generates embedding and inserts into database.
    """
    return add_memory_service(request, db)


@router.get("/", response_model=list[MemoryCardResponse])
def get_memories(db: Session = Depends(get_db)):
    """Fetch all career memory cards."""
    return get_all_memories_service(db)


@router.patch("/{memory_id}", response_model=MemoryCardResponse)
def update_memory(
    memory_id: int,
    request: UpdateMemoryRequest,
    db: Session = Depends(get_db),
):
    """Update a memory item. Re-generates embedding vector if content was modified."""
    return update_memory_service(memory_id, request, db)


@router.delete("/{memory_id}", response_model=DeleteResponse)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
):
    """Delete a memory item by ID."""
    return delete_memory_service(memory_id, db)
