from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.repository import (
    CodeSearchResultResponse,
    RepositoryResponse,
    SourceFileResponse,
)
from app.services import repository_queries

router = APIRouter()


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(db: Session = Depends(get_db)) -> list[RepositoryResponse]:
    return repository_queries.list_repositories(db)


@router.get("/repositories/{repository_id}", response_model=RepositoryResponse)
def get_repository(
    repository_id: int,
    db: Session = Depends(get_db),
) -> RepositoryResponse:
    repository = repository_queries.get_repository(db, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found.")

    return repository


@router.get("/repositories/{repository_id}/files", response_model=list[SourceFileResponse])
def list_repository_files(
    repository_id: int,
    db: Session = Depends(get_db),
) -> list[SourceFileResponse]:
    repository = repository_queries.get_repository(db, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found.")

    return repository_queries.list_repository_files(db, repository)


@router.get(
    "/repositories/{repository_id}/search",
    response_model=list[CodeSearchResultResponse],
)
def search_repository_code(
    repository_id: int,
    q: Annotated[str, Query(min_length=1)],
    db: Session = Depends(get_db),
) -> list[CodeSearchResultResponse]:
    repository = repository_queries.get_repository(db, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found.")

    return [
        CodeSearchResultResponse(
            file_path=source_file.path,
            symbol_name=code_chunk.symbol_name,
            symbol_type=code_chunk.symbol_type,
            start_line=code_chunk.start_line,
            end_line=code_chunk.end_line,
            docstring=code_chunk.docstring,
            source_code=code_chunk.source_code,
        )
        for source_file, code_chunk in repository_queries.search_repository_code(
            db,
            repository,
            q,
        )
    ]
