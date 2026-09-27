# Search quality evaluation

RepoPilot ranks one query with two methods. Keyword search is BM25 over
the symbol name, path, docstring, and source. Meaning search compares a
local embedding of the question with an embedding stored for each code
chunk. The list a person sees keeps an exact symbol name first, then
prefers a meaning match, and uses the keyword score to break ties.

## Method

`backend/eval_search_quality.py` indexes RepoPilot's own backend (`app/`,
20 files, 117 parsed symbols) with the real parser and the real database
models, in an in-memory SQLite database. It then runs the same 22
hand-written queries through keyword search, meaning search, and the
combined list.

Each expected answer was written by reading the source, including the
four questions whose words do not appear in the symbol name. The labels
were not changed after seeing the model output.

Meaning search uses `jinaai/jina-embeddings-v2-base-code` through
fastembed. The model runs locally on CPU. A chunk stays in the meaning
list when its cosine similarity is at least 0.34.

## Results

```
Keyword   Precision@1: 15/22 = 68.2%   Precision@3: 19/22 = 86.4%   MRR: 0.791
Meaning   Precision@1: 20/22 = 90.9%   Precision@3: 21/22 = 95.5%   MRR: 0.924
Combined  Precision@1: 20/22 = 90.9%   Precision@3: 21/22 = 95.5%   MRR: 0.931
```

Precision@1 asks whether the top result is the expected symbol.
Precision@3 asks whether that symbol is anywhere in the top 3. MRR is
the average of 1/rank, with 0 when the symbol is outside the top 10.

On the original 18 queries, keyword search was 15/18 at Precision@1.
The combined list is 17/18 on those same queries. It fixes the previous
keyword misses:

- "write repository index to database" now returns `write()` ahead of
  `DatabaseWriteError`.
- "list repositories" and "get repository by id" now return the query
  function ahead of the API route.
- "parsed code chunk dataclass" now returns `ParsedCodeChunk`.

Two questions that do not name the symbol also land on the right
function:

- "break a camel case name into separate words" returns `_tokenize`.
  Keyword search had ranked it 4th.
- "how rare a word is across the indexed code" returns
  `_bm25_field_score`. Keyword search did not place it in the top 10.

## What is still wrong

- **"save parsed symbols into the database"** still misses `write()`.
  The combined list returns `DatabaseWriter` at rank 7. Meaning search
  does not keep any chunk for this question, because the closest cosine
  is under 0.34, so the list falls back to keyword order.
- **"list files in a repository"** returns the API route at rank 1 and
  the service function `list_repository_files` at rank 3. Keyword search
  had the service function at rank 1. Meaning search prefers the route.

## Honest limits

- 22 queries can catch obvious ranking mistakes. They are not a
  statistical claim about every repository.
- The corpus is RepoPilot's own backend. The queries were written by
  someone who had read that code.
- The metric checks whether the expected symbol is near the top. It does
  not score the rest of the page.
- The first search after install downloads the embedding model.

## Running it

```bash
cd backend
python eval_search_quality.py
```

No database setup is required. The script uses in-memory SQLite and
discards it on exit. The first run downloads the embedding model.
