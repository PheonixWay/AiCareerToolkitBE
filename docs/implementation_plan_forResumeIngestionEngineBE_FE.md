# Resume Ingestion Engine — End-to-End Implementation Plan

> **Purpose**: This plan is written so each numbered step can be handed to a lower-cost model independently. Every step is self-contained, lists exact files to create/modify, and includes the complete code to write. No step requires knowledge of steps that haven't been done yet (aside from the explicit dependencies noted).

## Confirmed Environment State (already done by user)

| Item | Status |
|------|--------|
| `config.py` — `GROQ_API_KEY` | ✅ Already renamed from `OPENAI_API_KEY` |
| `config.py` — `GOOGLE_API_KEY` | ✅ Already added |
| `.env` — `GROQ_API_KEY` set | ✅ Already set |
| `.env` — `GOOGLE_API_KEY` set | ✅ Already set |
| Package manager | **uv** — use `uv add` / `pyproject.toml`, NOT `pip install` |

---

## Architecture Overview

```
PDF Upload / Text Input
        │
        ▼
[BE] Step 1: PDF Text Extraction  (PyMuPDF)
[BE] Step 2: LLM Structured Parsing  (Groq → JSON via Pydantic schema)
[BE] Step 3: Semantic Chunking  (one chunk per project/role/skill)
[BE] Step 4: Vector Embedding  (OpenAI text-embedding-3-small)
[BE] Step 5: pgvector Storage  (PostgreSQL + pgvector)
        │
        ▼
[FE] Career Memory Dashboard  (tabs: Experience | Projects | Skills | Education)
[FE] Upload Zone  (PDF drag-and-drop + progress states)
[FE] Add New Entry Modal  (lightweight text → embed → save)
[FE] Edit / Delete controls on every card
```

---

## PHASE 1 — Backend (Steps 1–9)

---

### STEP 1 — Install New Python Dependencies

**Goal**: Add `pymupdf`, `pgvector`, `python-multipart`, and `google-generativeai` to the project.

> **Package manager**: This project uses **uv**. Do NOT use `pip install`. Use `uv add` which updates `pyproject.toml` and `uv.lock` automatically.

**Action**: Run in the terminal (inside the BE project root):

```bash
uv add pymupdf pgvector python-multipart google-generativeai
```

This will automatically add the packages to [`pyproject.toml`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/pyproject.toml) under `dependencies` and regenerate `uv.lock`.

Also append these lines to [`requirements.txt`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/requirements.txt) so the file stays in sync for Docker/CI that uses it:

```
pymupdf>=1.25.5
pgvector>=0.4.1
python-multipart>=0.0.20
google-generativeai>=0.8.0
```

> **Why**: `pymupdf` (fitz) extracts text from PDFs. `pgvector` is the SQLAlchemy adapter for vector columns. `python-multipart` enables FastAPI file upload endpoints. `google-generativeai` is the official Google SDK for Gemini embeddings.

---

### STEP 2 — Enable pgvector in PostgreSQL

**Goal**: Enable the `vector` extension in your local Postgres DB so SQLAlchemy can store vector columns.

**Action**: Connect to your database and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

You can do this via `psql` or any DB GUI (DBeaver, TablePlus):
```bash
psql -U auth_app -d aicareer_db -h localhost -p 5433
```
Then paste the SQL above.

> **Why**: pgvector must be enabled per-database before any vector column can be created.

---

### STEP 3 — Create the `career_memory` SQLAlchemy Model

**Goal**: Define the database table that will store every memory chunk (text + embedding vector).

**File to create**:
`app/slices/memory/models.py` (**NEW FILE**)

```python
# app/slices/memory/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class CareerMemory(Base):
    __tablename__ = "career_memory"

    id = Column(Integer, primary_key=True, index=True)

    # The category of this chunk: "experience", "project", "skill", "education"
    category = Column(String(50), nullable=False, index=True)

    # The raw text of the chunk as shown on the UI card
    content = Column(Text, nullable=False)

    # Optional metadata: company name, project name, etc.
    title = Column(String(255), nullable=True)

    # The 768-dimension embedding vector from Google's text-embedding-004 model
    embedding = Column(Vector(768), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
```

> **Why**: This is the single table for all career memories. The `Vector(1536)` column stores the OpenAI embedding. The `category` column drives the tabs in the FE dashboard.

---

### STEP 4 — Create Pydantic Schemas for the Memory Slice

**Goal**: Define all request/response shapes for the memory API endpoints.

**File to create**:
`app/slices/memory/schemas.py` (**NEW FILE**)

```python
# app/slices/memory/schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ─── LLM Parsing Schema (internal — not exposed to API consumers) ─────────────
class ResumeChunk(BaseModel):
    category: str        # "experience" | "project" | "skill" | "education"
    title: str           # e.g. "Backend Developer @ Shopcardd"
    content: str         # The full paragraph text for this chunk


class ParsedResume(BaseModel):
    chunks: list[ResumeChunk]


# ─── API Request / Response Schemas ──────────────────────────────────────────
class AddMemoryRequest(BaseModel):
    """Used for the lightweight 'Add New Entry' flow (no PDF needed)."""
    category: str         # "experience" | "project" | "skill" | "education"
    title: str
    content: str


class MemoryCardResponse(BaseModel):
    """Represents a single memory card shown on the FE dashboard."""
    id: int
    category: str
    title: Optional[str]
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
```

---

### STEP 5 — Create the Memory Service (Core Business Logic)

**Goal**: Write the five-step ingestion pipeline and the lightweight add/query/delete logic.

**File to create**:
`app/slices/memory/service.py` (**NEW FILE**)

```python
# app/slices/memory/service.py
import json
import fitz  # PyMuPDF
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
import google.generativeai as genai

from app.core.aiClient import client
from app.core.config import settings
from .models import CareerMemory
from .schemas import (
    ParsedResume,
    AddMemoryRequest,
    MemoryCardResponse,
    IngestResponse,
    DeleteResponse,
    UpdateMemoryRequest,
)

# Configure Google Gemini client with the API key from settings
genai.configure(api_key=settings.GOOGLE_API_KEY)

# ─── INTERNAL HELPER: Generate Embedding ─────────────────────────────────────

def _get_embedding(text: str) -> list[float]:
    """Call Google Gemini's text-embedding-004 model to get a 768-dim vector.
    
    Uses GOOGLE_API_KEY from settings.
    NOTE: Google's embedding model returns 768 dimensions, not 1536.
    The Vector column in models.py must be Vector(768) to match.
    """
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document",
    )
    return result["embedding"]


# ─── STEP 1 + 2 + 3: PDF → Text → LLM → Chunks ──────────────────────────────

def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Step 1: Use PyMuPDF to extract raw text from a PDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text_blocks = []
    for page in doc:
        text_blocks.append(page.get_text("text"))
    return "\n".join(text_blocks)


def _parse_resume_with_llm(raw_text: str) -> ParsedResume:
    """Step 2+3: Ask the LLM to parse raw text into semantic chunks."""
    schema_json = json.dumps(ParsedResume.model_json_schema(), indent=2)

    prompt = f"""
You are an expert resume parser. Read the following resume text and convert it into structured semantic chunks.

Rules:
- Each job/internship role = ONE chunk with category "experience"
- Each project = ONE chunk with category "project"  
- All skills combined = ONE chunk with category "skill"
- Each education entry = ONE chunk with category "education"
- The "content" field should be a complete, self-contained paragraph describing that item
- The "title" field should be a short label like "Software Engineer @ Google" or "RAG Chatbot Project"

Respond ONLY with valid JSON matching this schema:
{schema_json}

Resume Text:
{raw_text}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": "You are a resume parser that strictly outputs valid JSON. No markdown, no explanation.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response during resume parsing.")

    return ParsedResume.model_validate_json(content)


# ─── PUBLIC SERVICE FUNCTIONS ─────────────────────────────────────────────────

def ingest_pdf_service(file: UploadFile, db: Session) -> IngestResponse:
    """Full 5-step pipeline: PDF → Text → LLM Parse → Embed → Store."""
    # Validate file type
    if file.content_type not in ("application/pdf",):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_bytes = file.file.read()

    # Step 1: Extract raw text
    raw_text = _extract_text_from_pdf(file_bytes)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from the PDF.")

    # Step 2+3: Parse into semantic chunks via LLM
    parsed = _parse_resume_with_llm(raw_text)

    # Step 4+5: Embed each chunk and store in DB
    saved_count = 0
    for chunk in parsed.chunks:
        embedding = _get_embedding(chunk.content)
        memory = CareerMemory(
            category=chunk.category,
            title=chunk.title,
            content=chunk.content,
            embedding=embedding,
        )
        db.add(memory)
        saved_count += 1

    db.commit()
    return IngestResponse(message="Resume ingested successfully.", chunks_saved=saved_count)


def add_memory_service(request: AddMemoryRequest, db: Session) -> MemoryCardResponse:
    """Lightweight add: skip PDF and LLM parsing, go straight to embed → store."""
    embedding = _get_embedding(request.content)
    memory = CareerMemory(
        category=request.category,
        title=request.title,
        content=request.content,
        embedding=embedding,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return MemoryCardResponse.model_validate(memory)


def get_all_memories_service(db: Session) -> list[MemoryCardResponse]:
    """Fetch all memory cards, ordered newest first."""
    memories = (
        db.query(CareerMemory)
        .order_by(CareerMemory.created_at.desc())
        .all()
    )
    return [MemoryCardResponse.model_validate(m) for m in memories]


def delete_memory_service(memory_id: int, db: Session) -> DeleteResponse:
    """Delete a single memory card by ID."""
    memory = db.query(CareerMemory).filter(CareerMemory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory entry not found.")
    db.delete(memory)
    db.commit()
    return DeleteResponse(message=f"Memory {memory_id} deleted.")


def update_memory_service(
    memory_id: int, request: UpdateMemoryRequest, db: Session
) -> MemoryCardResponse:
    """Update text fields of a memory card. Re-embeds content if content changed."""
    memory = db.query(CareerMemory).filter(CareerMemory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory entry not found.")

    if request.title is not None:
        memory.title = request.title  # type: ignore[assignment]
    if request.category is not None:
        memory.category = request.category  # type: ignore[assignment]
    if request.content is not None:
        memory.content = request.content  # type: ignore[assignment]
        # Re-generate embedding for updated content
        memory.embedding = _get_embedding(request.content)  # type: ignore[assignment]

    db.commit()
    db.refresh(memory)
    return MemoryCardResponse.model_validate(memory)
```

> **Important**: The `_get_embedding` function uses a **direct OpenAI client** (not the Groq-based `aiClient`) because Groq does not support the embeddings API. Make sure `OPENAI_API_KEY` in `.env` is a **real OpenAI key** (not the Groq key). You will need to update your `.env` to have both a `GROQ_API_KEY` for the LLM calls and an `OPENAI_API_KEY` for embeddings. See Step 6 for config changes.

---

### STEP 6 — Fix `aiClient.py` and `jd_extractor/service.py` to use `GROQ_API_KEY`

**Goal**: The user renamed `OPENAI_API_KEY` → `GROQ_API_KEY` in `config.py`. Two existing files still reference the old name and will crash on startup. Fix them.

> **Note**: `config.py` is already up to date (done by user). This step only touches `aiClient.py` and `jd_extractor/service.py`.

#### 6A — Update [`app/core/aiClient.py`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/core/aiClient.py)

Replace the entire file:

```python
# app/core/aiClient.py
from openai import OpenAI
from app.core.config import settings

# OpenAI-compatible client pointed at Groq's fast inference endpoint
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=settings.GROQ_API_KEY,
)
```

#### 6B — Verify [`app/slices/jd_extractor/service.py`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/slices/jd_extractor/service.py)

This file imports `client` from `aiClient` (not `settings` directly), so it does **not** need changes. The fix in `aiClient.py` above propagates automatically.

If the file imports `settings.OPENAI_API_KEY` directly anywhere, replace every occurrence with `settings.GROQ_API_KEY`.

---

### STEP 7 — Create the Memory Router (API Endpoints)

**Goal**: Wire up all 5 HTTP endpoints for the memory slice.

**File to create**:
`app/slices/memory/router.py` (**NEW FILE**)

```python
# app/slices/memory/router.py
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.slices.auth.dependencies import get_current_user
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
    """Upload a PDF resume. Runs the full 5-step ingestion pipeline."""
    return ingest_pdf_service(file, db)


@router.post("/add", response_model=MemoryCardResponse)
def add_memory(
    request: AddMemoryRequest,
    db: Session = Depends(get_db),
):
    """Add a single memory entry via text (skips PDF parsing)."""
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
    """Edit a memory card's text. Re-embeds if content changes."""
    return update_memory_service(memory_id, request, db)


@router.delete("/{memory_id}", response_model=DeleteResponse)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
):
    """Delete a memory card by ID."""
    return delete_memory_service(memory_id, db)
```

> **Note on Auth**: The `get_current_user` dependency import is shown for reference. Keep the endpoints open (no auth) for initial testing, then add `current_user = Depends(get_current_user)` per-endpoint once the full flow is verified.

---

### STEP 8 — Create `__init__.py` for the Memory Slice

**Goal**: Make the memory slice a proper Python package.

**File to create**:
`app/slices/memory/__init__.py` (**NEW FILE**)

```python
# app/slices/memory/__init__.py
```

(Empty file — just needed for Python imports to work.)

---

### STEP 9 — Register the Memory Router in `main.py`

**Goal**: Hook the memory router into the FastAPI app and auto-create the new DB table.

**File to modify**:
[`app/main.py`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/main.py)

Add these two lines in the correct positions:

**Add import** (after existing imports, around line 10):
```python
from app.slices.memory.router import router as memory_router
from app.slices.memory import models as memory_models  # noqa: F401 – registers table
```

**Add router registration** (at the bottom, after existing `app.include_router` calls):
```python
app.include_router(memory_router)
```

> **Why the `memory_models` import?** SQLAlchemy's `Base.metadata.create_all(bind=engine)` only creates tables for models that have been imported. Importing `memory_models` ensures `career_memory` table is created on startup.

---

## PHASE 2 — Frontend (Steps 10–16)

---

### STEP 10 — Update TypeScript Types for Memory

**Goal**: Replace the placeholder types in `memory.types.ts` with exact types that match the backend response.

**File to modify**:
[`src/types/memory.types.ts`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/types/memory.types.ts)

Replace the entire file with:

```typescript
// src/types/memory.types.ts

export type MemoryCategory = 'experience' | 'project' | 'skill' | 'education'

// ─── API Response ─────────────────────────────────────────────────────────────
export interface MemoryCard {
  id: number
  category: MemoryCategory
  title: string | null
  content: string
  created_at: string  // ISO datetime string
}

// ─── Ingest PDF ───────────────────────────────────────────────────────────────
export interface IngestPdfResponse {
  message: string
  chunks_saved: number
}

// ─── Add Memory (text) ────────────────────────────────────────────────────────
export interface AddMemoryRequest {
  category: MemoryCategory
  title: string
  content: string
}

// ─── Update Memory ────────────────────────────────────────────────────────────
export interface UpdateMemoryRequest {
  category?: MemoryCategory
  title?: string
  content?: string
}

// ─── Legacy — kept for backward compat with any old imports ──────────────────
/** @deprecated Use AddMemoryRequest instead */
export interface MemoryIngestRequest {
  content: string
}

/** @deprecated Use IngestPdfResponse or MemoryCard instead */
export interface MemoryIngestResponse {
  [key: string]: unknown
}

export interface MemoryQueryRequest {
  query: string
}

export interface MemoryQueryResponse {
  [key: string]: unknown
}
```

---

### STEP 11 — Update API Endpoints and Memory Service

**Goal**: Add the new endpoint paths and service functions for all memory CRUD operations.

**File to modify**:
[`src/api/endpoints.ts`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/api/endpoints.ts)

Replace the `memory` section:

```typescript
// src/api/endpoints.ts
export const API_ENDPOINTS = {
  auth: {
    login: '/api/v1/auth/login',
  },
  jd: {
    extract: '/api/v1/jd/extract',
  },
  ats: {
    extract: '/api/v1/ats/extract',
  },
  resume: {
    generate: '/api/v1/resume/generate',
  },
  memory: {
    ingestPdf:  '/api/v1/memory/ingest-pdf',
    add:        '/api/v1/memory/add',
    getAll:     '/api/v1/memory/',
    update:     (id: number) => `/api/v1/memory/${id}`,
    delete:     (id: number) => `/api/v1/memory/${id}`,
  },
} as const
```

**File to modify**:
[`src/api/services/memory.service.ts`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/api/services/memory.service.ts)

Replace the entire file with:

```typescript
// src/api/services/memory.service.ts
import { api } from '@/api/client'
import { API_ENDPOINTS } from '@/api/endpoints'
import type {
  MemoryCard,
  IngestPdfResponse,
  AddMemoryRequest,
  UpdateMemoryRequest,
} from '@/types/memory.types'

/** Upload a PDF file — runs the full 5-step ingestion pipeline on the backend. */
export const ingestPdf = async (file: File): Promise<IngestPdfResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post<IngestPdfResponse>(
    API_ENDPOINTS.memory.ingestPdf,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

/** Fetch all career memory cards. */
export const getAllMemories = async (): Promise<MemoryCard[]> => {
  const { data } = await api.get<MemoryCard[]>(API_ENDPOINTS.memory.getAll)
  return data
}

/** Add a single memory entry via plain text (no PDF). */
export const addMemory = async (payload: AddMemoryRequest): Promise<MemoryCard> => {
  const { data } = await api.post<MemoryCard>(API_ENDPOINTS.memory.add, payload)
  return data
}

/** Update a memory card's text fields. */
export const updateMemory = async (
  id: number,
  payload: UpdateMemoryRequest,
): Promise<MemoryCard> => {
  const { data } = await api.patch<MemoryCard>(API_ENDPOINTS.memory.update(id), payload)
  return data
}

/** Delete a memory card. */
export const deleteMemory = async (id: number): Promise<void> => {
  await api.delete(API_ENDPOINTS.memory.delete(id))
}
```

---

### STEP 12 — Create the Zustand Memory Store

**Goal**: Centralize all memory state (cards, loading, upload progress) in a Zustand store.

**File to create**:
`src/stores/memory.store.ts` (**NEW FILE**)

```typescript
// src/stores/memory.store.ts
import { create } from 'zustand'
import type { MemoryCard, AddMemoryRequest, UpdateMemoryRequest } from '@/types/memory.types'
import {
  getAllMemories,
  ingestPdf,
  addMemory,
  updateMemory,
  deleteMemory,
} from '@/api/services/memory.service'

interface MemoryState {
  cards: MemoryCard[]
  isLoading: boolean
  isUploading: boolean
  uploadProgress: number   // 0-100
  error: string | null

  // Actions
  fetchMemories: () => Promise<void>
  uploadPdf: (file: File) => Promise<{ chunks_saved: number }>
  addEntry: (payload: AddMemoryRequest) => Promise<void>
  editEntry: (id: number, payload: UpdateMemoryRequest) => Promise<void>
  removeEntry: (id: number) => Promise<void>
  clearError: () => void
}

export const useMemoryStore = create<MemoryState>((set, get) => ({
  cards: [],
  isLoading: false,
  isUploading: false,
  uploadProgress: 0,
  error: null,

  fetchMemories: async () => {
    set({ isLoading: true, error: null })
    try {
      const cards = await getAllMemories()
      set({ cards })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch memories.'
      set({ error: msg })
    } finally {
      set({ isLoading: false })
    }
  },

  uploadPdf: async (file: File) => {
    set({ isUploading: true, uploadProgress: 10, error: null })
    try {
      set({ uploadProgress: 40 })
      const result = await ingestPdf(file)
      set({ uploadProgress: 90 })
      await get().fetchMemories()
      set({ uploadProgress: 100 })
      return result
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'PDF upload failed.'
      set({ error: msg })
      throw err
    } finally {
      setTimeout(() => set({ isUploading: false, uploadProgress: 0 }), 800)
    }
  },

  addEntry: async (payload) => {
    set({ isLoading: true, error: null })
    try {
      const newCard = await addMemory(payload)
      set((state) => ({ cards: [newCard, ...state.cards] }))
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to add memory.'
      set({ error: msg })
      throw err
    } finally {
      set({ isLoading: false })
    }
  },

  editEntry: async (id, payload) => {
    set({ error: null })
    try {
      const updated = await updateMemory(id, payload)
      set((state) => ({
        cards: state.cards.map((c) => (c.id === id ? updated : c)),
      }))
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update memory.'
      set({ error: msg })
      throw err
    }
  },

  removeEntry: async (id) => {
    set({ error: null })
    try {
      await deleteMemory(id)
      set((state) => ({ cards: state.cards.filter((c) => c.id !== id) }))
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete memory.'
      set({ error: msg })
      throw err
    }
  },

  clearError: () => set({ error: null }),
}))
```

---

### STEP 13 — Create Child UI Components

**Goal**: Build the three reusable sub-components used inside `MemoryBankPage`.

#### 13A — `PdfUploadZone.tsx`

**File to create**:
`src/components/memory/PdfUploadZone.tsx` (**NEW FILE**)

```tsx
// src/components/memory/PdfUploadZone.tsx
import { type FC, useRef, useState, useCallback } from 'react'
import { Upload, FileText, Loader2 } from 'lucide-react'

interface Props {
  onFileSelected: (file: File) => void
  isUploading: boolean
  uploadProgress: number
}

export const PdfUploadZone: FC<Props> = ({ onFileSelected, isUploading, uploadProgress }) => {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragOver, setIsDragOver] = useState(false)

  const handleFile = useCallback(
    (file: File) => {
      if (file.type !== 'application/pdf') {
        alert('Only PDF files are accepted.')
        return
      }
      onFileSelected(file)
    },
    [onFileSelected],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setIsDragOver(true) }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={onDrop}
      onClick={() => !isUploading && inputRef.current?.click()}
      className={`
        relative flex flex-col items-center justify-center gap-4
        rounded-2xl border-2 border-dashed p-12 cursor-pointer
        transition-all duration-300 select-none
        ${isDragOver
          ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
          : 'border-slate-300 bg-slate-50 hover:border-emerald-400 hover:bg-emerald-50/50 dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-emerald-500 dark:hover:bg-emerald-900/10'
        }
        ${isUploading ? 'pointer-events-none opacity-80' : ''}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
      />

      {isUploading ? (
        <>
          <Loader2 className="h-12 w-12 animate-spin text-emerald-500" />
          <div className="w-full max-w-xs">
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
              <div
                className="h-2 rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="mt-2 text-center text-sm text-slate-500 dark:text-slate-400">
              Processing your resume… {uploadProgress}%
            </p>
          </div>
        </>
      ) : (
        <>
          <div className="rounded-2xl bg-emerald-100 p-4 dark:bg-emerald-900/30">
            <Upload className="h-8 w-8 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="text-center">
            <p className="text-base font-semibold text-slate-800 dark:text-slate-100">
              Set up your Career Memory Bank
            </p>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Drag &amp; drop your latest resume PDF here, or{' '}
              <span className="text-emerald-600 underline dark:text-emerald-400">click to browse</span>
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
            <FileText className="h-3.5 w-3.5" />
            PDF files only — max 10 MB
          </div>
        </>
      )}
    </div>
  )
}
```

#### 13B — `MemoryCard.tsx`

**File to create**:
`src/components/memory/MemoryCard.tsx` (**NEW FILE**)

```tsx
// src/components/memory/MemoryCard.tsx
import { type FC, useState } from 'react'
import { Pencil, Trash2, Check, X } from 'lucide-react'
import type { MemoryCard as MemoryCardType, UpdateMemoryRequest } from '@/types/memory.types'

interface Props {
  card: MemoryCardType
  onDelete: (id: number) => void
  onEdit: (id: number, payload: UpdateMemoryRequest) => void
}

export const MemoryCard: FC<Props> = ({ card, onDelete, onEdit }) => {
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(card.title ?? '')
  const [editContent, setEditContent] = useState(card.content)

  const handleSave = () => {
    onEdit(card.id, { title: editTitle, content: editContent })
    setIsEditing(false)
  }

  const handleCancel = () => {
    setEditTitle(card.title ?? '')
    setEditContent(card.content)
    setIsEditing(false)
  }

  return (
    <div className="group relative rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md dark:border-slate-700 dark:bg-slate-800/60">
      {/* Edit / Delete Controls */}
      <div className="absolute right-3 top-3 flex items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
        {isEditing ? (
          <>
            <button
              onClick={handleSave}
              title="Save"
              className="rounded-lg p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleCancel}
              title="Cancel"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => setIsEditing(true)}
              title="Edit"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => onDelete(card.id)}
              title="Delete"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}
      </div>

      {/* Card Content */}
      {isEditing ? (
        <div className="space-y-2 pr-16">
          <input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-400 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
            placeholder="Title"
          />
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={4}
            className="w-full resize-none rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
          />
        </div>
      ) : (
        <div className="pr-16">
          {card.title && (
            <p className="mb-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
              {card.title}
            </p>
          )}
          <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
            {card.content}
          </p>
          <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
            {new Date(card.created_at).toLocaleDateString('en-US', {
              month: 'short', day: 'numeric', year: 'numeric',
            })}
          </p>
        </div>
      )}
    </div>
  )
}
```

#### 13C — `AddEntryModal.tsx`

**File to create**:
`src/components/memory/AddEntryModal.tsx` (**NEW FILE**)

```tsx
// src/components/memory/AddEntryModal.tsx
import { type FC, useState } from 'react'
import { X, Plus, Loader2 } from 'lucide-react'
import type { AddMemoryRequest, MemoryCategory } from '@/types/memory.types'

interface Props {
  onClose: () => void
  onSubmit: (payload: AddMemoryRequest) => Promise<void>
}

const CATEGORIES: { value: MemoryCategory; label: string }[] = [
  { value: 'experience', label: '💼 Work Experience' },
  { value: 'project',    label: '🚀 Project' },
  { value: 'skill',      label: '🛠 Skill' },
  { value: 'education',  label: '🎓 Education' },
]

export const AddEntryModal: FC<Props> = ({ onClose, onSubmit }) => {
  const [category, setCategory] = useState<MemoryCategory>('experience')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!title.trim() || !content.trim()) {
      setError('Title and description are required.')
      return
    }
    setIsSubmitting(true)
    setError(null)
    try {
      await onSubmit({ category, title: title.trim(), content: content.trim() })
      onClose()
    } catch {
      setError('Failed to add entry. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-50">
            Add New Memory Entry
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Category Selector */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-400">
            Category
          </label>
          <div className="grid grid-cols-2 gap-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.value}
                onClick={() => setCategory(cat.value)}
                className={`rounded-xl border px-3 py-2 text-sm font-medium transition-colors ${
                  category === cat.value
                    ? 'border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : 'border-slate-200 text-slate-600 hover:border-emerald-300 dark:border-slate-700 dark:text-slate-400'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Title */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-400">
            Title
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder='e.g. "Software Engineer @ Google" or "RAG Chatbot"'
            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>

        {/* Content */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-400">
            Description
          </label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={5}
            placeholder="Describe this experience, project, or skill in detail…"
            className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>

        {error && (
          <p className="mb-3 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </p>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-xl px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Add to Memory
          </button>
        </div>
      </div>
    </div>
  )
}
```

---

### STEP 14 — Create a barrel `index.ts` for the memory components

**Goal**: Clean re-export so the page imports are tidy.

**File to create**:
`src/components/memory/index.ts` (**NEW FILE**)

```typescript
// src/components/memory/index.ts
export { PdfUploadZone } from './PdfUploadZone'
export { MemoryCard } from './MemoryCard'
export { AddEntryModal } from './AddEntryModal'
```

---

### STEP 15 — Rewrite `MemoryBankPage.tsx` (The Main Dashboard)

**Goal**: Replace the placeholder page with the full, functional Career Memory Bank dashboard.

**File to modify**:
[`src/pages/memory-bank/MemoryBankPage.tsx`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/pages/memory-bank/MemoryBankPage.tsx)

Replace the entire file with:

```tsx
// src/pages/memory-bank/MemoryBankPage.tsx
import { type FC, useEffect, useState } from 'react'
import { Brain, Plus, Loader2, AlertCircle, Upload } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { PdfUploadZone } from '@/components/memory/PdfUploadZone'
import { MemoryCard } from '@/components/memory/MemoryCard'
import { AddEntryModal } from '@/components/memory/AddEntryModal'
import { useMemoryStore } from '@/stores/memory.store'
import type { MemoryCategory, UpdateMemoryRequest } from '@/types/memory.types'

const TABS: { value: MemoryCategory | 'all'; label: string }[] = [
  { value: 'all',        label: 'All' },
  { value: 'experience', label: '💼 Experience' },
  { value: 'project',    label: '🚀 Projects' },
  { value: 'skill',      label: '🛠 Skills' },
  { value: 'education',  label: '🎓 Education' },
]

export const MemoryBankPage: FC = () => {
  const {
    cards, isLoading, isUploading, uploadProgress, error,
    fetchMemories, uploadPdf, addEntry, editEntry, removeEntry, clearError,
  } = useMemoryStore()

  const [activeTab, setActiveTab] = useState<MemoryCategory | 'all'>('all')
  const [showAddModal, setShowAddModal] = useState(false)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)

  useEffect(() => {
    fetchMemories()
  }, [fetchMemories])

  const handlePdfUpload = async (file: File) => {
    try {
      const result = await uploadPdf(file)
      setUploadSuccess(`✅ Resume ingested! ${result.chunks_saved} memory chunks created.`)
      setTimeout(() => setUploadSuccess(null), 6000)
    } catch {
      // error is already in store
    }
  }

  const handleEdit = (id: number, payload: UpdateMemoryRequest) => {
    editEntry(id, payload)
  }

  const filtered =
    activeTab === 'all' ? cards : cards.filter((c) => c.category === activeTab)

  const isEmpty = cards.length === 0

  return (
    <div className="animate-fadeIn space-y-6">
      <div className="flex items-center justify-between">
        <PageHeader
          title="Career Memory Bank"
          subtitle="Your personal AI knowledge base — built from your career history."
        />
        {!isEmpty && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Add Entry
            </button>
          </div>
        )}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 dark:border-red-800 dark:bg-red-900/20">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          <button onClick={clearError} className="ml-auto text-red-500 hover:text-red-700">✕</button>
        </div>
      )}

      {/* Success Banner */}
      {uploadSuccess && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
          {uploadSuccess}
        </div>
      )}

      {/* Onboarding: Empty State → Show Upload Zone */}
      {isEmpty && !isLoading && (
        <div className="space-y-4">
          <PdfUploadZone
            onFileSelected={handlePdfUpload}
            isUploading={isUploading}
            uploadProgress={uploadProgress}
          />
          <div className="flex items-center gap-3">
            <div className="flex-1 border-t border-slate-200 dark:border-slate-700" />
            <span className="text-xs text-slate-400">or</span>
            <div className="flex-1 border-t border-slate-200 dark:border-slate-700" />
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 py-4 text-sm font-medium text-slate-500 hover:border-emerald-400 hover:text-emerald-600 dark:border-slate-700 dark:hover:border-emerald-500 dark:hover:text-emerald-400 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add first entry manually
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        </div>
      )}

      {/* Dashboard: Has Memories */}
      {!isEmpty && !isLoading && (
        <>
          {/* Upload More Banner */}
          {!isUploading && (
            <div
              className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-500 hover:border-emerald-400 hover:text-emerald-600 dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-emerald-500 dark:hover:text-emerald-400 transition-colors"
              onClick={() => document.getElementById('pdf-re-upload')?.click()}
            >
              <Upload className="h-4 w-4" />
              Re-upload a newer resume to add more memories
              <input
                id="pdf-re-upload"
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePdfUpload(f) }}
              />
            </div>
          )}
          {isUploading && (
            <div className="overflow-hidden rounded-xl border border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-900/20">
              <div
                className="h-1.5 bg-emerald-500 transition-all duration-500"
                style={{ width: `${uploadProgress}%` }}
              />
              <p className="px-4 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                Processing resume… {uploadProgress}%
              </p>
            </div>
          )}

          {/* Tabs */}
          <div className="flex gap-1 overflow-x-auto">
            {TABS.map((tab) => {
              const count = tab.value === 'all'
                ? cards.length
                : cards.filter((c) => c.category === tab.value).length
              return (
                <button
                  key={tab.value}
                  onClick={() => setActiveTab(tab.value)}
                  className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
                    activeTab === tab.value
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                  }`}
                >
                  {tab.label}
                  <span className={`rounded-full px-1.5 py-0.5 text-xs ${
                    activeTab === tab.value
                      ? 'bg-emerald-500 text-white'
                      : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400'
                  }`}>
                    {count}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Memory Cards Grid */}
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50 py-16 dark:border-slate-700 dark:bg-slate-800/30">
              <Brain className="h-10 w-10 text-slate-300 dark:text-slate-600" />
              <p className="text-sm text-slate-400 dark:text-slate-500">
                No {activeTab === 'all' ? '' : activeTab} entries yet
              </p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((card) => (
                <MemoryCard
                  key={card.id}
                  card={card}
                  onDelete={removeEntry}
                  onEdit={handleEdit}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Add Entry Modal */}
      {showAddModal && (
        <AddEntryModal
          onClose={() => setShowAddModal(false)}
          onSubmit={addEntry}
        />
      )}
    </div>
  )
}
```

---

### STEP 16 — Final Wiring Check

**Goal**: Verify nothing is broken and all pieces are connected.

#### 16A — Verify `src/stores/memory.store.ts` is importable
Make sure `zustand` is installed. Check `package.json` — if `"zustand"` is not listed, run:
```bash
npm install zustand
```

#### 16B — Check `src/routes/` to confirm MemoryBankPage route exists
Open the routing file (likely `src/routes/index.tsx` or `App.tsx`) and confirm the route for `/memory-bank` or equivalent already renders `<MemoryBankPage />`. If not, add it following the same pattern as other routes.

#### 16C — Backend: Verify `app/slices/auth/dependencies.py` exports `get_current_user`
Open [`app/slices/auth/dependencies.py`](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/slices/auth/dependencies.py) — the memory router imports this. If the function name is different, update the import in `app/slices/memory/router.py`.

#### 16D — Restart the backend
```bash
cd AiCareerToolkitBE
uvicorn app.main:app --reload --port 8000
```

Check that the startup logs show the `career_memory` table being created.

#### 16E — Test with Swagger UI
Navigate to `http://localhost:8000/docs` and test:
1. `POST /api/v1/memory/ingest-pdf` — upload a PDF
2. `GET /api/v1/memory/` — verify chunks were stored
3. `POST /api/v1/memory/add` — add a manual entry
4. `PATCH /api/v1/memory/{id}` — edit an entry
5. `DELETE /api/v1/memory/{id}` — delete an entry

---

## Summary of All Files

### Backend — New Files
| File | Action |
|------|--------|
| `app/slices/memory/__init__.py` | NEW |
| `app/slices/memory/models.py` | NEW — uses `Vector(768)` for Gemini embeddings |
| `app/slices/memory/schemas.py` | NEW |
| `app/slices/memory/service.py` | NEW — uses `google-generativeai` for embeddings |
| `app/slices/memory/router.py` | NEW |

### Backend — Modified Files
| File | Change |
|------|--------|
| `pyproject.toml` | `uv add pymupdf pgvector python-multipart google-generativeai` |
| `requirements.txt` | Append 4 new packages (for Docker/CI sync) |
| `app/core/config.py` | ✅ Already done — `GROQ_API_KEY` + `GOOGLE_API_KEY` |
| `.env` | ✅ Already done — both keys set |
| `app/core/aiClient.py` | Fix: `settings.OPENAI_API_KEY` → `settings.GROQ_API_KEY` |
| `app/main.py` | Import + register `memory_router` |

### Frontend — New Files
| File | Action |
|------|--------|
| `src/components/memory/PdfUploadZone.tsx` | NEW |
| `src/components/memory/MemoryCard.tsx` | NEW |
| `src/components/memory/AddEntryModal.tsx` | NEW |
| `src/components/memory/index.ts` | NEW |
| `src/stores/memory.store.ts` | NEW |

### Frontend — Modified Files
| File | Change |
|------|--------|
| `src/types/memory.types.ts` | Replace placeholders with real types |
| `src/api/endpoints.ts` | Add full memory endpoint map |
| `src/api/services/memory.service.ts` | Replace with full CRUD service |
| `src/pages/memory-bank/MemoryBankPage.tsx` | Full rewrite |

---

## Key Architectural Decisions

> [!IMPORTANT]
> **Two separate AI clients**: `aiClient.py` uses **Groq** (OpenAI-compatible, `GROQ_API_KEY`) for fast LLM chat completions. Embeddings use **Google Gemini** (`GOOGLE_API_KEY`, `google-generativeai` SDK). Both keys are already set in `.env`.

> [!IMPORTANT]
> **Embedding dimensions changed**: Google's `text-embedding-004` returns **768 dimensions**, not 1536 like OpenAI. The `CareerMemory` model uses `Vector(768)`. Make sure pgvector extension is enabled BEFORE the app starts, or `create_all()` will fail.

> [!NOTE]
> **Package manager is `uv`**. Run `uv add <package>` to install dependencies. This updates `pyproject.toml` and `uv.lock`. Also manually append to `requirements.txt` so Docker/CI stays in sync.

> [!NOTE]
> pgvector requires `CREATE EXTENSION IF NOT EXISTS vector;` to be run once in the PostgreSQL database BEFORE starting the app. After that, `Base.metadata.create_all()` handles the table creation automatically.

> [!TIP]
> When handing Steps 1–9 to a lower-cost model, give each step independently. Order: **1→2→3→4→5→6→7→8→9**. Steps 10–16 (frontend) are independent of each other but require Steps 1–9 to be done first.
