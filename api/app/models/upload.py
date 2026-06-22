from sqlalchemy import Column, String, Text, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import UUIDBase


class UploadedFile(UUIDBase):
    __tablename__ = "uploaded_files"

    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf | docx | xlsx | csv | png | jpg
    file_path = Column(String(500), nullable=False)
    parsed_content = Column(Text, nullable=True)
    module = Column(String(50), nullable=False)  # family | company
    entity_id = Column(UUID(as_uuid=True), nullable=True)  # linked budget or event id

    embeddings = relationship("FileEmbedding", back_populates="file", cascade="all, delete-orphan")


class FileEmbedding(UUIDBase):
    __tablename__ = "file_embeddings"

    file_id = Column(UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    chroma_embedding_id = Column(String(100), nullable=True)

    file = relationship("UploadedFile", back_populates="embeddings")
