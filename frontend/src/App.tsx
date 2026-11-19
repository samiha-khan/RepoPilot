import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import "./App.css";
import { Highlight, docstringSummary, isTestPath, queryTerms } from "./highlight";

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

type IndexResponse = {
  repository: Repository;
  total_files: number;
  total_chunks: number;
  skipped_files: number;
};

const SEARCH_LIMIT = 50;

// Well-known libraries to try when nothing is indexed yet.
const EXAMPLE_REPOSITORIES = [
  "https://github.com/psf/requests",
  "https://github.com/pallets/click",
  "https://github.com/pallets/flask",
];

// Shareable links look like ?repo=3&q=parse+a+date. They are read once on load.
const initialParams = new URLSearchParams(window.location.search);
const initialRepositoryId = Number(initialParams.get("repo")) || undefined;
const initialQuery = initialParams.get("q") ?? "";

function githubUrl(repository: Repository, result: SearchResult): string {
  // "HEAD" resolves to the repository's default branch on GitHub.
  return `${repository.url}/blob/HEAD/${result.file_path}#L${result.start_line}-L${result.end_line}`;
}

const apiUrl = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, options);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const errorBody = (await response.json()) as { detail?: string };
      message = errorBody.detail ?? message;
    } catch {
      // Keep the generic status message when the API does not return JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function App() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [serverSlow, setServerSlow] = useState(false);
  const [copied, setCopied] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [repositoriesLoading, setRepositoriesLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [indexLoading, setIndexLoading] = useState(false);
  const [indexMessage, setIndexMessage] = useState<string | null>(null);
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

  const canIndex = repositoryUrl.trim().length > 0 && !indexLoading;

  const loadRepositories = useCallback(
    async (
      preferredRepositoryId?: number,
      shouldApply: () => boolean = () => true,
    ) => {
      setRepositoriesLoading(true);
      setError(null);
      // Free hosting pauses idle servers; say so instead of looking broken.
      const slowTimer = window.setTimeout(() => setServerSlow(true), 3000);

      try {
        const loadedRepositories =
          await fetchJson<Repository[]>("/repositories");

        if (!shouldApply()) {
          return;
        }

        setRepositories(loadedRepositories);
        if (loadedRepositories.length === 0) {
          setSelectedRepositoryId("");
          return;
        }

        const preferredRepository = loadedRepositories.find(
          (repository) => repository.id === preferredRepositoryId,
        );
        setSelectedRepositoryId(
          String(preferredRepository?.id ?? loadedRepositories[0].id),
        );
      } catch (loadError) {
        if (shouldApply()) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load repositories.",
          );
        }
      } finally {
        window.clearTimeout(slowTimer);
        if (shouldApply()) {
          setServerSlow(false);
          setRepositoriesLoading(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    let isActive = true;

    void loadRepositories(initialRepositoryId, () => isActive);

    return () => {
      isActive = false;
    };
  }, [loadRepositories]);

  async function handleIndexRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canIndex) {
      return;
    }

    setIndexLoading(true);
    setIndexMessage(null);
    setError(null);

    try {
      const indexResult = await fetchJson<IndexResponse>("/repositories/index", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: repositoryUrl.trim() }),
      });

      setRepositoryUrl("");
      setResults([]);
      setSelectedResult(null);
      setHasSearched(false);
      setIndexMessage(
        `Indexed ${indexResult.repository.owner}/${indexResult.repository.name}: ${indexResult.total_files} Python files, ${indexResult.total_chunks} code chunks.`,
      );
      await loadRepositories(indexResult.repository.id);
    } catch (indexError) {
      setIndexMessage(null);
      setError(
        indexError instanceof Error
          ? indexError.message
          : "Unable to index repository.",
      );
    } finally {
      setIndexLoading(false);
    }
  }

  const runSearch = useCallback(async (repositoryId: string, text: string) => {
    const trimmed = text.trim();
    if (!repositoryId || trimmed.length === 0) {
      return;
    }

    setSearchLoading(true);
    setError(null);
    setHasSearched(true);
    setSelectedResult(null);
    setSearchedQuery(trimmed);
    window.history.replaceState(
      null,
      "",
      `?repo=${repositoryId}&q=${encodeURIComponent(trimmed)}`,
    );

    try {
      const searchResults = await fetchJson<SearchResult[]>(
        `/repositories/${repositoryId}/search?q=${encodeURIComponent(
          trimmed,
        )}&limit=${SEARCH_LIMIT}`,
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
  }, []);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runSearch(selectedRepositoryId, query);
  }

  function applySuggestion(text: string) {
    setQuery(text);
    void runSearch(selectedRepositoryId, text);
  }

  async function copySource() {
    if (!selectedResult) {
      return;
    }
    try {
      await navigator.clipboard.writeText(selectedResult.source_code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Copying is not available in this browser.");
    }
  }

  // Example searches taken from the selected repository's own docstrings.
  useEffect(() => {
    setSuggestions([]);
    if (!selectedRepositoryId) {
      return;
    }
    let isActive = true;
    fetchJson<string[]>(`/repositories/${selectedRepositoryId}/suggestions`)
      .then((items) => {
        if (isActive) {
          setSuggestions(items);
        }
      })
      .catch(() => undefined);
    return () => {
      isActive = false;
    };
  }, [selectedRepositoryId]);

  // A link with ?q=... runs its search once the repository list has loaded.
  const ranInitialSearch = useRef(false);
  useEffect(() => {
    if (!ranInitialSearch.current && selectedRepositoryId && initialQuery) {
      ranInitialSearch.current = true;
      void runSearch(selectedRepositoryId, initialQuery);
    }
  }, [selectedRepositoryId, runSearch]);

  // Press "/" anywhere to jump to the search box.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) {
        event.preventDefault();
        searchInput.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const highlightTerms = useMemo(() => queryTerms(searchedQuery), [searchedQuery]);

  return (
    <main className="app-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">RepoPilot</p>
          <h1>Repository code search</h1>
          <p className="description">
            Find functions and classes in a Python repository by describing what
            they do or by typing a name. Press <kbd>/</kbd> to jump to the search
            box.
          </p>
        </div>
      </header>

      <section className="controls" aria-label="Repository search controls">
        <form className="index-form" onSubmit={handleIndexRepository}>
          <label className="field repository-url-field">
            <span>Index a repository</span>
            <input
              type="url"
              value={repositoryUrl}
              onChange={(event) => setRepositoryUrl(event.target.value)}
              placeholder="https://github.com/owner/repository"
            />
          </label>
          <button type="submit" disabled={!canIndex}>
            {indexLoading ? "Indexing..." : "Index"}
          </button>
        </form>

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
              ref={searchInput}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Describe what you need, or type a name"
            />
          </label>
          <button type="submit" disabled={!canSearch}>
            {searchLoading ? "Searching" : "Search"}
          </button>
        </form>
      </section>

      {indexMessage ? <div className="status success">{indexMessage}</div> : null}
      {selectedRepository ? (
        <section className="repository-summary">
          <a href={selectedRepository.url} target="_blank" rel="noreferrer">
            {selectedRepository.url}
          </a>
          {suggestions.length > 0 ? (
            <span className="suggestions">
              <span>Try:</span>
              {suggestions.map((text) => (
                <button
                  className="chip"
                  key={text}
                  onClick={() => applySuggestion(text)}
                  type="button"
                >
                  {text}
                </button>
              ))}
            </span>
          ) : null}
        </section>
      ) : null}
      {serverSlow ? (
        <div className="status">
          Waking the server. Free hosting pauses when idle, so the first request
          can take up to 30 seconds.
        </div>
      ) : null}

      {error ? <div className="status error">{error}</div> : null}
      {repositoriesLoading ? (
        <div className="status">Loading repositories...</div>
      ) : null}
      {!repositoriesLoading && repositories.length === 0 ? (
        <div className="status">
          No repositories are indexed yet. Paste a public GitHub URL above, or
          pick an example to fill it in:
          <span className="suggestions">
            {EXAMPLE_REPOSITORIES.map((url) => (
              <button
                className="chip"
                key={url}
                onClick={() => setRepositoryUrl(url)}
                type="button"
              >
                {url.replace("https://github.com/", "")}
              </button>
            ))}
          </span>
        </div>
      ) : null}

      <section className="content-grid">
        <div className="results-panel">
          <div className="panel-header">
            <h2>Results</h2>
            {hasSearched && !searchLoading ? (
              <span>{results.length === SEARCH_LIMIT ? `Top ${SEARCH_LIMIT}` : `${results.length} matches`}</span>
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
                <span className="file-path">
                  <Highlight text={result.file_path} terms={highlightTerms} />
                </span>
                <span className="symbol-row">
                  <strong>
                    <Highlight text={result.symbol_name} terms={highlightTerms} />
                  </strong>
                  <span>{result.symbol_type}</span>
                  {isTestPath(result.file_path) ? <span>test</span> : null}
                </span>
                <span className="line-range">
                  Lines {result.start_line}-{result.end_line}
                </span>
                {result.docstring ? (
                  <span className="docstring">
                    <Highlight
                      text={docstringSummary(result.docstring)}
                      terms={highlightTerms}
                    />
                  </span>
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
                  {selectedResult.symbol_name} · lines {selectedResult.start_line}-
                  {selectedResult.end_line}
                </span>
                <span className="preview-actions">
                  {selectedRepository ? (
                    <a
                      href={githubUrl(selectedRepository, selectedResult)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open on GitHub
                    </a>
                  ) : null}
                  <button className="link-button" onClick={copySource} type="button">
                    {copied ? "Copied" : "Copy code"}
                  </button>
                </span>
              </div>
              <pre>
                <code>
                  <Highlight text={selectedResult.source_code} terms={highlightTerms} />
                </code>
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
