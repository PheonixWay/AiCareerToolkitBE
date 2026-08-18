# app/slices/memory/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class CareerMemory(Base):
    __tablename__ = "career_memory"

    id = Column(Integer, primary_key=True, index=True)

    # Category of the memory chunk: "experience", "project", "skill", "education"
    category = Column(String(50), nullable=False, index=True)

    # Detailed text content of the chunk
    content = Column(Text, nullable=False)

    # Short title or header label (e.g. "Software Engineer @ Acme Corp")
    title = Column(String(255), nullable=True)

    # Vector embedding representation (3072-dim from Google Gemini gemini-embedding-001)
    embedding = Column(Vector(3072), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
