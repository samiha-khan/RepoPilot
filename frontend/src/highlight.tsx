// Highlights the words of a search query inside result text.
//
// This only affects display. The backend decides what matches; here a query
// word is marked wherever it occurs as a substring (case-insensitive), so
// "cookiejar" is marked inside `cookiejar_from_dict`, and a word like
// "parsing" also marks "parse" and "parsed" through a crude suffix trim.

const STOPWORDS = new Set(
  (
    "a an the of for to in on at by with from into over and or but not is are " +
    "was were be been being this that these those it its as if then do does did " +
    "how what which who when where why can could should would i we you my our " +
    "your me us there here"
  ).split(" "),
);

export function queryTerms(query: string): string[] {
  const words = query.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return [...new Set(words.filter((word) => word.length > 1 && !STOPWORDS.has(word)))];
}

function trimSuffix(word: string): string {
  return word.length > 4 ? word.replace(/(ing|ed|es|s)$/, "") : word;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function Highlight({ text, terms }: { text: string; terms: string[] }) {
  if (terms.length === 0 || text.length === 0) {
    return <>{text}</>;
  }

  const pattern = new RegExp(
    `(${terms.map((term) => escapeRegExp(trimSuffix(term))).join("|")})`,
    "gi",
  );
  // Splitting on a capturing group puts the matched text at the odd indexes.
  const parts = text.split(pattern);

  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? <mark key={index}>{part}</mark> : part,
      )}
    </>
  );
}

const TEST_PATH = /(^|\/)(tests?|testing)\/|(^|\/)test_[^/]*\.py$|_test\.py$|(^|\/)conftest\.py$/;

export function isTestPath(path: string): boolean {
  return TEST_PATH.test(path);
}

// The part of a docstring before the first blank line or ":param" style field,
// on one line. Result cards show this; the preview shows the full source.
export function docstringSummary(docstring: string): string {
  const summary = docstring.split(/\n\s*\n|\n\s*:/)[0];
  return summary.replace(/\s+/g, " ").trim();
}
