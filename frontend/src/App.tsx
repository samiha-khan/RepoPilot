import { FormEvent, useEffect, useMemo, useState } from "react";

import "./App.css";

type Repository = {
  id: number;
  owner: string;
  name: string;
  url: string;
  default_branch: string | null;
  created_at: string;
  updated_at: string;
};

type SearchResult = {
  file_path: string;
  symbol_name: string;
  symbol_type: string;
  start_line: number;
  end_line: number;
  docstring: string | null;
  source_code: string;
};

const apiUrl = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function App() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [repositoriesLoading, setRepositoriesLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const selectedRepository = useMemo(
    () =>
      repositories.find(
        (repository) => repository.id === Number(selectedRepositoryId),
      ) ?? null,
    [repositories, selectedRepositoryId],
  );

  const canSearch =
    selectedRepositoryId.length > 0 && query.trim().length > 0 && !searchLoading;

  useEffect(() => {
    let isActive = true;

    async function loadRepositories() {
      setRepositoriesLoading(true);
      setError(null);

      try {
        const loadedRepositories =
          await fetchJson<Repository[]>("/repositories");

        if (!isActive) {
          return;
        }

        setRepositories(loadedRepositories);
        if (loadedRepositories.length > 0) {
          setSelectedRepositoryId(String(loadedRepositories[0].id));
        }
      } catch (loadError) {
        if (isActive) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load repositories.",
          );
        }
      } finally {
        if (isActive) {
          setRepositoriesLoading(false);
        }
      }
    }

    void loadRepositories();

    return () => {
      isActive = false;
    };
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canSearch) {
      return;
    }

    setSearchLoading(true);
    setError(null);
    setHasSearched(true);
    setSelectedResult(null);

    try {
      const searchResults = await fetchJson<SearchResult[]>(
        `/repositories/${selectedRepositoryId}/search?q=${encodeURIComponent(
          query.trim(),
        )}`,
      );
      setResults(searchResults);
      setSelectedResult(searchResults[0] ?? null);
    } catch (searchError) {
      setResults([]);
      setError(
        searchError instanceof Error
          ? searchError.message
          : "Unable to search repository.",
      );
    } finally {
      setSearchLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">RepoPilot</p>
          <h1>Repository code search</h1>
          <p className="description">
            Browse indexed Python repositories and inspect matching code chunks
            stored by the backend indexer.
          </p>
        </div>
      </header>

      <section className="controls" aria-label="Repository search controls">
        <label className="field">
          <span>Repository</span>
          <select
            value={selectedRepositoryId}
            onChange={(event) => {
              setSelectedRepositoryId(event.target.value);
              setResults([]);
              setSelectedResult(null);
              setHasSearched(false);
            }}
            disabled={repositoriesLoading || repositories.length === 0}
          >
            {repositories.length === 0 ? (
              <option value="">No repositories indexed</option>
            ) : (
              repositories.map((repository) => (
                <option key={repository.id} value={repository.id}>
                  {repository.owner}/{repository.name}
                </option>
              ))
            )}
          </select>
        </label>

        <form className="search-form" onSubmit={handleSearch}>
          <label className="field search-field">
            <span>Search code</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Symbol, docstring, path, or source"
            />
          </label>
          <button type="submit" disabled={!canSearch}>
            {searchLoading ? "Searching" : "Search"}
          </button>
        </form>
      </section>

      {selectedRepository ? (
        <section className="repository-summary">
          <span>{selectedRepository.url}</span>
          <span>
            Default branch: {selectedRepository.default_branch ?? "unknown"}
          </span>
        </section>
      ) : null}

      {error ? <div className="status error">{error}</div> : null}
      {repositoriesLoading ? (
        <div className="status">Loading repositories...</div>
      ) : null}
      {!repositoriesLoading && repositories.length === 0 ? (
        <div className="status">
          No repositories are indexed yet. Run the CLI index command first.
        </div>
      ) : null}

      <section className="content-grid">
        <div className="results-panel">
          <div className="panel-header">
            <h2>Results</h2>
            {hasSearched && !searchLoading ? (
              <span>{results.length} matches</span>
            ) : null}
          </div>

          {searchLoading ? <div className="status">Searching...</div> : null}
          {hasSearched && !searchLoading && results.length === 0 && !error ? (
            <div className="status">No matching code chunks found.</div>
          ) : null}

          <div className="result-list">
            {results.map((result) => (
              <button
                className={
                  selectedResult === result ? "result-card active" : "result-card"
                }
                key={`${result.file_path}:${result.start_line}:${result.symbol_name}`}
                onClick={() => setSelectedResult(result)}
                type="button"
              >
                <span className="file-path">{result.file_path}</span>
                <span className="symbol-row">
                  <strong>{result.symbol_name}</strong>
                  <span>{result.symbol_type}</span>
                </span>
                <span className="line-range">
                  Lines {result.start_line}-{result.end_line}
                </span>
                {result.docstring ? (
                  <span className="docstring">{result.docstring}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>

        <aside className="preview-panel" aria-label="Source preview">
          <div className="panel-header">
            <h2>Source Preview</h2>
          </div>
          {selectedResult ? (
            <>
              <div className="preview-meta">
                <span>{selectedResult.file_path}</span>
                <span>
                  {selectedResult.symbol_name} · {selectedResult.start_line}-
                  {selectedResult.end_line}
                </span>
              </div>
              <pre>
                <code>{selectedResult.source_code}</code>
              </pre>
            </>
          ) : (
            <div className="status">Select a result to inspect its source.</div>
          )}
        </aside>
      </section>
    </main>
  );
}

export default App;
