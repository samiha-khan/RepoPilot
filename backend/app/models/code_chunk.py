from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CodeChunk(Base):
    __tablename__ = "code_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_file_id",
            "symbol_name",
            "symbol_type",
            "start_line",
            "end_line",
            name="uq_code_chunks_identity",
        ),
        CheckConstraint("start_line > 0", name="ck_code_chunks_start_line_positive"),
        CheckConstraint("end_line >= start_line", name="ck_code_chunks_valid_line_range"),
        Index("ix_code_chunks_source_file_id", "source_file_id"),
        Index("ix_code_chunks_symbol_name", "symbol_name"),
        Index("ix_code_chunks_symbol_type", "symbol_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_name: Mapped[str] = mapped_column(String(512), nullable=False)
    symbol_type: Mapped[str] = mapped_column(String(100), nullable=False)
    start_line: Mapped[int] = mapped_column(nullable=False)
    end_line: Mapped[int] = mapped_column(nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    source_file: Mapped["SourceFile"] = relationship(back_populates="code_chunks")
