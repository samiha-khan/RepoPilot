# Search quality evaluation

RepoPilot's BM25 ranker had unit tests but no evaluation of whether the
ranking itself is actually good. This closes that gap.

## Method

`backend/eval_search_quality.py` indexes RepoPilot's own backend (`app/`,
19 files, 90 parsed functions/classes/methods) using the real parser and
the real database models, in-memory SQLite instead of Postgres so it runs
standalone. It then runs 18 hand-written queries through the actual
`search_repository_code()` function used in production, not a
reimplementation.

Each query's expected answer was written by reading the real source
before running anything, e.g. querying "bm25 field score" and expecting
`_bm25_field_score` in `repository_queries.py`, because that function
exists and does that. Nothing here was reverse-engineered from what the
ranker happened to return.

## Results

```
Precision@1: 15/18 = 83.3%
Precision@3: 18/18 = 100.0%
MRR:         0.917
```

Precision@1 asks: is the single top result the one you wanted? Precision@3
asks: is it somewhere in the top 3? MRR (mean reciprocal rank) is the
average of 1/rank across all queries, so a query answered at rank 1 scores
1.0, rank 2 scores 0.5, and so on.

## The two near-misses

Two queries landed the right answer at rank 2 instead of rank 1:

- **"list repositories"** ranked the API route handler
  (`app/api/repositories.py`) above the underlying query function
  (`app/services/repository_queries.py::list_repositories`). Both
  literally contain the phrase, and the route handler's file path
  contains "repositories" as an exact substring, which BM25 rewards.
  Reasonable behavior, not a bug, just not what a specific query had in
  mind.
- **"write repository index to database"** ranked the `DatabaseWriteError`
  exception class above the actual `write()` method that does the writing.
  This is the more informative one: pure keyword scoring doesn't
  distinguish "this class is about writing" from "this class handles
  errors when writing," because both contexts contain the same words. A
  semantic/embedding-based ranker would likely do better here, since it
  could distinguish "the thing that writes" from "the thing that reports
  writing failed" by meaning rather than just term overlap. Worth
  keeping in mind if this project's search is ever extended.

## Hybrid search (BM25 plus embeddings)

The `write()` near-miss above, plus the general point that BM25 needs
shared vocabulary, led me to add an optional hybrid mode. Each chunk
(symbol name, path, docstring, first 2,000 characters of source) is
embedded with BGE-small through fastembed at index time. At query time
the BM25 ranking and the top 20 nearest chunks by cosine similarity are
merged with reciprocal rank fusion (k=60). If a result's symbol name is
exactly the query, it stays on top, since fusion can otherwise push it
down.

The original 18 queries mostly reuse words from the code, so they can't
show what embeddings add. I wrote 12 more that describe the code without
using its names, with expected answers taken from reading the code, same
as before. For example "turn blank strings into none" should find
`_clean_metadata_value` in `cli.py`.

Adding the embedding code to `app/` changed the indexed corpus to 20
files and 109 chunks. BM25 still scores the same on the original set.

| Query set | Mode | Precision@1 | Precision@3 | MRR |
|---|---|---|---|---|
| Original (18) | BM25 | 15/18 = 83.3% | 18/18 = 100.0% | 0.917 |
| Original (18) | Hybrid | 14/18 = 77.8% | 18/18 = 100.0% | 0.889 |
| Differently worded (12) | BM25 | 4/12 = 33.3% | 6/12 = 50.0% | 0.438 |
| Differently worded (12) | Hybrid | 7/12 = 58.3% | 7/12 = 58.3% | 0.631 |

What hybrid got right that BM25 didn't:

- "write repository index to database" now returns `write()` first
  instead of `DatabaseWriteError`, the exact case described above.
- "turn blank strings into none" (rank 4 to 1), "prevent path traversal
  when unpacking an archive" (2 to 1), and "fix heroku postgres
  connection string" (2 to 1).

What it got worse:

- Four of the original queries ("search repository code", "list
  repositories", "get repository by id", "list files in a repository")
  now rank the API route handler first and the service function second.
  Both have the same name and nearly the same words, and the embeddings
  can't tell them apart either. Net effect is one fewer top-1 hit than
  BM25.

Still missed by both:

- "skip node_modules and virtualenv folders" (`_is_excluded`). The
  function body only references `EXCLUDED_DIRECTORIES`; the folder names
  live in a constant that isn't part of the chunk.
- "which frontend domains can call the api" (`allowed_cors_origins`).
  It's a few lines with no docstring, so there's little text to embed.
- "make sure a path stays within the project root", "liveness check
  endpoint", and "combine keyword and vector rankings" weren't in BM25's
  top 10 at all. Hybrid moved them to ranks 4, 5, and 8, closer but still
  outside the top 3.

The takeaway: hybrid is clearly better when the query doesn't share
words with the code, a little worse when it does, so BM25 stays the
default and hybrid is opt-in. Twelve queries is a small set, so I'd
treat the gap as a direction, not a precise number. Hybrid hasn't been
run on the external psf/requests eval yet.

Run it with:

```bash
cd backend
pip install -r requirements-embeddings.txt
python eval_search_quality.py --mode hybrid
```

## Honest limitations of this evaluation

- **The corpus is the code under test.** The internal eval indexes
  RepoPilot's own `app/`, so adding search code changes what's being
  searched. Numbers from different commits aren't directly comparable;
  `compare_search_modes.py` runs every setup on the same snapshot so
  comparisons within one run are fair.

- **18 queries is small.** It's enough to catch obvious ranking problems,
  not enough to make a statistically confident claim about ranking
  quality in general.
- **Evaluated against RepoPilot's own codebase.** That's a defensible
  choice, since it's a codebase I can write accurate expected-answers
  for, but it also means the queries and the corpus have some shared
  vocabulary (this is Python code about parsing and searching Python
  code), which could make results look slightly better than they would
  on a domain the queries weren't written by someone who knows the code
  as well.
- **Every "OK" here is objectively-correct-symbol-found, not
  subjectively-good-result.** The metric doesn't capture whether the
  *ranking of everything else* on the page is sensible, only whether the
  one expected answer showed up near the top.

## Running it

```bash
cd backend
python eval_search_quality.py
```

No database setup needed, it uses an in-memory SQLite instance and
discards it when the script exits.

## External validation: does this hold up on a codebase it wasn't tuned on?

The limitation above (shared vocabulary with RepoPilot's own code) isn't
hypothetical. `backend/eval_search_quality_external.py` runs the identical
method, same real parser, same real `search_repository_code()`, against
[psf/requests](https://github.com/psf/requests): a well-known HTTP library
with no relationship to RepoPilot, so there's no shared-vocabulary
advantage. 18 queries, again written by reading the real `requests` source
in `src/requests/*.py` before running anything, each expected symbol name
checked for global uniqueness across the package first.

```
Precision@1: 10/18 = 55.6%
Precision@3: 17/18 = 94.4%
MRR:         0.729
```

Compared to the self-evaluation above (83.3% / 100.0% / 0.917), Precision@1
drops by almost 28 points on a genuinely external codebase, while
Precision@3 and MRR hold up much better (94.4% and 0.729 vs. 100% and
0.917). That gap is the honest answer to the limitation flagged above: this
ranker generalizes to code it's never seen, but is noticeably worse at
putting the *single best* answer in the #1 slot once there's no shared
vocabulary between the query author and the codebase.

Every one of the 8 near-misses and the 1 miss follows the same mechanism:
a shorter or more literally-matching symbol beats the intended one on raw
term overlap. For example, `'send a get request'` (rank 8, the one actual
miss) ranked `Session.send` above `get`, because the query's own word
"send" is a literal, exact match against that method's name, which BM25
rewards regardless of what the query actually meant. `'connection timeout
error'` similarly ranked the parent class `ConnectionError` above the
intended `ConnectTimeout`, because "connection" and "error" are both
literally in `ConnectionError`'s name while `ConnectTimeout` only matches
on "connection." This is the same root cause as the `database_writer.py`
near-miss in the self-evaluation above, not a new failure mode, just a
more frequent one once the query vocabulary isn't guaranteed to match the
code's vocabulary.

Honest limitations of this external check, same spirit as above: 18
queries against one external codebase is still small, `requests` is
itself clean, well-documented Python close in style to RepoPilot's own
code (a messier or more idiosyncratically-named codebase would likely
fare worse), and the near-miss/miss classification above is my own
reading of *why* each case ranked the way it did, not something the
ranker itself reports.

Needs a local clone of `psf/requests` (not installed via pip, the actual
source tree):

```bash
git clone --depth 1 https://github.com/psf/requests.git /tmp/requests
cd backend
python eval_search_quality_external.py --requests-src /tmp/requests/src/requests
```
