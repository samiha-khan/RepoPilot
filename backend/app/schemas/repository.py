from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner: str
    name: str
    url: str
    default_branch: str | None
    created_at: datetime
    updated_at: datetime


class SourceFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    language: str
    sha256: str
    size: int
    created_at: datetime
    updated_at: datetime


class CodeSearchResultResponse(BaseModel):
    file_path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    docstring: str | None
    source_code: str
    matched_by: list[str]
    keyword_rank: int | None
    meaning_rank: int | None
    why: str


class RepositoryIndexRequest(BaseModel):
    url: str


class RepositoryIndexResponse(BaseModel):
    repository: RepositoryResponse
    total_files: int
    total_chunks: int
    skipped_files: int
