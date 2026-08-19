# app/slices/memory/service.py
import json
import pymupdf 
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from google import genai
from google.genai import types
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
    RetrievalTestRequest,
    RetrievalResultItem,
    RetrievalTestResponse,
)

# Instantiate the new google.genai client
_genai_client = genai.Client(api_key=settings.GOOGLE_API_KEY)


# ─── INTERNAL HELPER: Generate Embedding via Google Gemini ───────────────────
def _get_embedding(text: str,task_type: str) -> list[float]:
    """Call Google Gemini text-embedding-001 to generate a 3072-dim vector.
    
    Uses the new google.genai SDK (google-genai package).
    """
    try:
        result = _genai_client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type
            ),
        )
        return result.embeddings[0].values
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate embedding via Google Gemini: {str(e)}",
        )


# ─── STEP 1: Extract Text from PDF using PyMuPDF ─────────────────────────────
def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Use PyMuPDF to extract clean text blocks from each PDF page."""
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        text_blocks = []
        for page in doc:
            text_blocks.append(page.get_text("text"))
        return "\n".join(text_blocks)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error reading PDF content: {str(e)}",
        )


# ─── STEP 2 + 3: Structured Parsing via LLM (Semantic Chunking) ──────────────
def _parse_resume_with_llm(raw_text: str) -> ParsedResume:
    """Pass extracted resume text to LLM to enforce structured JSON semantic chunks."""
    schema_dict = ParsedResume.model_json_schema()
    schema_json = json.dumps(schema_dict, indent=2)

    prompt = f"""
        You are an expert resume parser and career data architect.
        Analyze the following resume text and parse it into structured semantic chunks.

        Rules for Chunking:
        1. Each work experience or internship role MUST be an isolated chunk with category "experience".
        2. Each individual project MUST be an isolated chunk with category "project".
        3. Key skills, tools, and technical competencies should be a chunk with category "skill".
        4. Each educational qualification (Degree, University) MUST be a chunk with category "education".
        5. The "title" field must be a short, clean summary label (e.g. "Software Engineer @ Acme", "E-Commerce App Project", "Core Technical Skills", "B.Tech in Computer Science").
        6. The "content" field must be the full descriptive paragraph retaining all key metrics, responsibilities, and technologies.

        CRITICAL INSTRUCTION: You MUST respond ONLY with a valid JSON object matching this schema:
        {schema_json}

        Resume Text:
        {raw_text}
        """

    messages = [
        {
            "role": "system",
            "content": "You are a highly analytical AI that strictly outputs valid JSON matching the exact schema provided by the user, without any markdown formatting or extra text.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    except Exception as e:
        if "404" in str(e) or "model_not_found" in str(e):
            response = client.chat.completions.create(
                model="qwen/qwen3.6-27b",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        else:
            raise e

    result_text = response.choices[0].message.content
    if not result_text:
        raise HTTPException(
            status_code=500,
            detail="AI model returned an empty response while parsing the resume.",
        )

    return ParsedResume.model_validate_json(result_text)


# ─── PUBLIC SERVICE FUNCTIONS ─────────────────────────────────────────────────

def ingest_pdf_service(file: UploadFile, db: Session) -> IngestResponse:
    """Full 5-step pipeline: PDF Upload → PyMuPDF Text → LLM JSON → Gemini Embeddings → pgvector DB."""
    if file.filename and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded PDF file is empty.")

    # Step 1: Extract Text
    raw_text = _extract_text_from_pdf(file_bytes)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract readable text from the PDF.")

    # Step 2 + 3: Parse into semantic chunks
    parsed = _parse_resume_with_llm(raw_text)

    if not parsed.chunks:
        raise HTTPException(status_code=400, detail="No valid career chunks could be extracted from resume.")

    # Step 4 + 5: Embed each chunk and store in PostgreSQL pgvector
    saved_count = 0
    for chunk in parsed.chunks:
        embedding = _get_embedding(chunk.content,task_type="retrieval_document")
        memory = CareerMemory(
            category=chunk.category.lower().strip(),
            title=chunk.title.strip() if chunk.title else None,
            content=chunk.content.strip(),
            embedding=embedding,
        )
        db.add(memory)
        saved_count += 1

    db.commit()
    return IngestResponse(
        message="Resume successfully ingested into Career Memory Bank.",
        chunks_saved=saved_count,
    )


def add_memory_service(request: AddMemoryRequest, db: Session) -> MemoryCardResponse:
    """Direct text input: skip PDF extraction & LLM parsing → generate embedding → store."""
    embedding = _get_embedding(request.content,task_type="retrieval_document")
    memory = CareerMemory(
        category=request.category.lower().strip(),
        title=request.title.strip() if request.title else None,
        content=request.content.strip(),
        embedding=embedding,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return MemoryCardResponse.model_validate(memory)


def get_all_memories_service(db: Session) -> list[MemoryCardResponse]:
    """Retrieve all ingested memory cards ordered by latest created."""
    memories = (
        db.query(CareerMemory)
        .order_by(CareerMemory.created_at.desc())
        .all()
    )
    return [MemoryCardResponse.model_validate(m) for m in memories]


def delete_memory_service(memory_id: int, db: Session) -> DeleteResponse:
    """Delete a memory item by ID."""
    memory = db.query(CareerMemory).filter(CareerMemory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory entry not found.")

    db.delete(memory)
    db.commit()
    return DeleteResponse(message=f"Memory #{memory_id} successfully deleted.")


def update_memory_service(
    memory_id: int, request: UpdateMemoryRequest, db: Session
) -> MemoryCardResponse:
    """Update title/category/content of a memory card. Re-generates embedding if content changed."""
    memory = db.query(CareerMemory).filter(CareerMemory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory entry not found.")

    if request.title is not None:
        memory.title = request.title.strip()  # type: ignore[assignment]
    if request.category is not None:
        memory.category = request.category.lower().strip()  # type: ignore[assignment]
    if request.content is not None and request.content.strip():
        memory.content = request.content.strip()  # type: ignore[assignment]
        memory.embedding = _get_embedding(request.content.strip(),task_type="retrieval_document") 

    db.commit()
    db.refresh(memory)
    return MemoryCardResponse.model_validate(memory)


def test_retrieval_service(
    request: RetrievalTestRequest, db: Session
) -> RetrievalTestResponse:
    """Dev/Debug service: Generate query vector with task_type='retrieval_query' and perform Cosine Similarity search in pgvector."""
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Generate embedding vector for query
    query_embedding = _get_embedding(query_text, task_type="retrieval_query")

    # Cosine distance in pgvector is <=>
    # Cosine similarity = 1 - cosine_distance
    distance_expr = CareerMemory.embedding.cosine_distance(query_embedding)

    rows = (
        db.query(
            CareerMemory.id,
            CareerMemory.title,
            CareerMemory.category,
            CareerMemory.content,
            CareerMemory.created_at,
            (1 - distance_expr).label("similarity_score"),
        )
        .filter(CareerMemory.embedding.isnot(None))
        .order_by(distance_expr.asc())
        .limit(max(1, min(request.top_k, 50)))
        .all()
    )

    results = [
        RetrievalResultItem(
            id=row.id,
            title=row.title,
            category=row.category,
            content=row.content,
            similarity_score=float(row.similarity_score) if row.similarity_score is not None else 0.0,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return RetrievalTestResponse(
        query=query_text,
        total_results=len(results),
        results=results,
    )

