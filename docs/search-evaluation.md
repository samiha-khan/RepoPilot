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

## Honest limitations of this evaluation

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
