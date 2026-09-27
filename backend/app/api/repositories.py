from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.repository import (
    CodeSearchResultResponse,
    RepositoryIndexRequest,
    RepositoryIndexResponse,
    RepositoryResponse,
    SourceFileResponse,
)
from app.services.embeddings import get_embedder
from app.services.public_repository_indexer import (
    InvalidPublicRepositoryUrlError,
    PublicRepositoryIndexError,
    RepositoryArchiveNotFoundError,
    RepositoryArchiveTooLargeError,
    index_public_github_repository,
)
from app.services import repository_queries

router = APIRouter()


@router.post("/repositories/index", response_model=RepositoryIndexResponse)
def index_repository(request: RepositoryIndexRequest) -> RepositoryIndexResponse:
    try:
        summary = index_public_github_repository(request.url, embed=True)
    except InvalidPublicRepositoryUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryArchiveNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RepositoryArchiveTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except PublicRepositoryIndexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RepositoryIndexResponse(
        repository=summary.repository,
        total_files=summary.total_files,
        total_chunks=summary.total_chunks,
        skipped_files=summary.skipped_files,
    )


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
            file_path=hit.source_file.path,
            symbol_name=hit.code_chunk.symbol_name,
            symbol_type=hit.code_chunk.symbol_type,
            start_line=hit.code_chunk.start_line,
            end_line=hit.code_chunk.end_line,
            docstring=hit.code_chunk.docstring,
            source_code=hit.code_chunk.source_code,
            matched_by=hit.matched_by,
            keyword_rank=hit.keyword_rank,
            meaning_rank=hit.meaning_rank,
            why=hit.why,
        )
        for hit in repository_queries.search_repository_code(
            db,
            repository,
            q,
            embedder=get_embedder() if _repository_has_embeddings(db, repository) else None,
        )
    ]


def _repository_has_embeddings(db: Session, repository) -> bool:
    from sqlalchemy import select

    from app.models import CodeChunk, SourceFile

    embedding = db.scalar(
        select(CodeChunk.embedding)
        .join(SourceFile, CodeChunk.source_file_id == SourceFile.id)
        .where(SourceFile.repository_id == repository.id)
        .where(CodeChunk.embedding.is_not(None))
        .limit(1)
    )
    return embedding is not None
