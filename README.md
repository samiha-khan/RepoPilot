# RepoPilot

RepoPilot is a full-stack application for indexing and searching Python repositories. It parses Python source code using AST, stores repository and code metadata in PostgreSQL, and provides a web interface for searching and viewing indexed code.

## Features

- Load repositories from a local Git path or GitHub HTTPS URL
- Parse Python functions, async functions, classes, and methods using AST
- Store repository, source file, and code chunk data in PostgreSQL
- Index repositories from the command line
- Search across symbol names, file paths, docstrings, and source code
- Rank search results using BM25-style scoring
- Browse indexed repositories and preview source code through the web interface
- Run the full application locally with Docker Compose
- Automated backend test suite with 78 tests

## Tech Stack

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL
- psycopg
- GitPython
- Typer
- pytest

### Frontend

- React
- TypeScript
- Vite
- CSS

### Development

- Docker
- Docker Compose

## Project Structure

```text
backend/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
    cli.py
    main.py
  tests/

frontend/
  src/

docker/
  postgres/

docker-compose.yml
```

## Running Locally

Start the application:

```bash
docker compose up --build
```

Open the frontend at:

```text
http://localhost:5173
```

The backend API is available at:

```text
http://localhost:8000
```

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

## Indexing a Repository

Create the database tables if needed:

```bash
docker compose exec backend python -c "from app.db.base import Base; from app.db.session import engine; import app.models; Base.metadata.create_all(engine)"
```

Index the repository mounted at `/workspace`:

```bash
docker compose exec backend python -m app.cli index /workspace
```

You can also index another repository available inside the container:

```bash
docker compose exec backend python -m app.cli index /path/to/repo \
  --owner owner-name \
  --name repo-name \
  --url https://github.com/owner-name/repo-name
```

## Search

RepoPilot searches indexed code across:

- Symbol names
- File paths
- Docstrings
- Source code

Results are ranked using lightweight BM25-style scoring with higher weight given to symbol names and file paths. Exact and partial symbol matches receive additional ranking priority.

## API

The backend provides the following endpoints:

```text
GET /health
GET /repositories
GET /repositories/{repository_id}
GET /repositories/{repository_id}/files
GET /repositories/{repository_id}/search?q=<query>
```

## Running Tests

Tests use a separate PostgreSQL test database.

Run the backend test suite with:

```bash
docker compose exec backend python -m pytest tests
```

Current test result:

```text
78 passed
```
