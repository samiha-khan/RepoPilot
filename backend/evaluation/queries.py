"""Hand-labelled queries.

Each entry is (query, expected symbol name, substring of the expected file
path). The expected answers were written from reading the source before any
ranker was run on them.
"""

# Against RepoPilot's own backend (``backend/app``).
REPOPILOT_QUERIES: list[tuple[str, str, str]] = [
    ("parse_file", "parse_file", "python_parser.py"),
    ("parse a python file", "parse_file", "python_parser.py"),
    ("bm25 field score", "_bm25_field_score", "repository_queries.py"),
    ("compute bm25 score for a field", "_bm25_field_score", "repository_queries.py"),
    ("tokenize", "_tokenize", "repository_queries.py"),
    ("search repository code", "search_repository_code", "repository_queries.py"),
    ("list repositories", "list_repositories", "repository_queries.py"),
    ("get repository by id", "get_repository", "repository_queries.py"),
    ("build search corpus", "_build_search_corpus", "repository_queries.py"),
    ("parse class methods", "_parse_class_methods", "python_parser.py"),
    ("python parse error", "PythonParseError", "python_parser.py"),
    ("parsed code chunk dataclass", "ParsedCodeChunk", "python_parser.py"),
    ("get source code for a node", "_get_source_code", "python_parser.py"),
    ("app config settings", "Settings", "config.py"),
    ("index repository from cli", "index", "cli.py"),
    ("write repository index to database", "write", "database_writer.py"),
    ("find search candidates", "_find_search_candidates", "repository_queries.py"),
    ("list files in a repository", "list_repository_files", "repository_queries.py"),
]

# Against psf/requests (``src/requests``). Where a name occurs in more than
# one file (get, post, cookiejar_from_dict) the path substring disambiguates.
REQUESTS_QUERIES: list[tuple[str, str, str]] = [
    ("get", "get", "api.py"),
    ("send a get request", "get", "api.py"),
    ("post", "post", "api.py"),
    ("basic auth", "HTTPBasicAuth", "auth.py"),
    ("digest authentication", "HTTPDigestAuth", "auth.py"),
    ("case insensitive dictionary", "CaseInsensitiveDict", "structures.py"),
    ("ambiguous request exception", "RequestException", "exceptions.py"),
    ("connection timeout error", "ConnectTimeout", "exceptions.py"),
    ("too many redirects", "TooManyRedirects", "exceptions.py"),
    ("build a cookiejar from a dict", "cookiejar_from_dict", "cookies.py"),
    ("convert a cookiejar to a dict", "dict_from_cookiejar", "utils.py"),
    ("guess json encoding from bytes", "guess_json_utf", "utils.py"),
    ("get encoding from http headers", "get_encoding_from_headers", "utils.py"),
    ("re-quote a uri", "requote_uri", "utils.py"),
    ("should we bypass proxies for this url", "should_bypass_proxies", "utils.py"),
    ("default user agent string", "default_user_agent", "utils.py"),
    ("json decode error", "JSONDecodeError", "exceptions.py"),
    ("raise exception for http error status", "raise_for_status", "models.py"),
]
