# Search ranking: design and evaluation

This document explains how RepoPilot ranks results, why it changed from the
first version, and how each decision was checked. Every number below comes
from the files in [`backend/evaluation/results/`](../backend/evaluation/results/)
and can be regenerated with the commands at the end.

## What was wrong with the first ranker

The first version found candidates with SQL `ILIKE '%term%'`, then scored them
with BM25 summed over four fields plus fixed bonuses for exact (+100) and
partial (+25) symbol-name matches. Reading it again, five problems stand out:

1. **Statistics came from the wrong set.** Document frequencies were counted
   over the candidate chunks (the ones that already matched), not the whole
   repository. A word that appears in every candidate looks common even if it
   is rare in the repository, so inverse document frequency was distorted.
2. **Substring candidate retrieval.** A query containing "a" matched almost
   every chunk, and `%` and `_` typed by a user acted as SQL wildcards.
3. **Weak identifier handling.** Only `camelCase` boundaries were split, so
   `HTTPBasicAuth` was not understood as HTTP + Basic + Auth. There was no
   stemming and no stopword handling for natural-language queries.
4. **Classes competed with their own methods.** A class chunk contains the
   source of all its methods, which are also separate chunks, so a class matched
   every query that matched any of its methods.
5. **Hand-set constants, never measured.** Field weights and the two bonuses
   had no evidence behind them.

## What the ranker does now

Code is in [`backend/app/search/`](../backend/app/search/).

- **Fields and BM25F.** Each chunk has four fields: symbol name, file path,
  docstring, body. Scoring follows BM25F (Robertson, Zaragoza and Taylor,
  CIKM 2004): term frequencies are length-normalised per field, multiplied by
  the field weight and added together, and only then passed through BM25's
  saturation. A word that appears in both the name and the body therefore
  cannot be counted twice at full strength, which summing per-field BM25
  scores does allow. The IDF form is `ln(1 + (N - n + 0.5) / (n + 0.5))`, the
  one Lucene uses (see Kamphuis et al., ECIR 2020, on BM25 variants), with `N`
  and `n` counted over the whole repository.
- **Tokenizer for code.** `parse_file`, `parseFile` and `HTTPBasicAuth` are
  split into words; words are stemmed with the Snowball English stemmer;
  English function words ("a", "the", "for") are dropped from queries but
  "get", "set", "list" and "run" are kept, because they are meaningful in code.
- **Exact name first.** A symbol whose name equals the query (ignoring case) is
  placed above everything else. BM25F orders results inside each group. This is
  an ordering rule, not an added score, so it cannot be outweighed.
- **Classes are indexed by what is theirs.** A class chunk is indexed by its
  header, docstring and class-level statements, plus the names of its methods,
  not by method bodies. The full source is still shown in the UI. This follows
  the idea in cAST (Zhang et al., 2025) that retrieval units should be
  self-contained and not duplicate each other's text.
- **Overload stubs are not indexed.** Functions decorated with
  `@overload` exist only for type checkers and repeat the name of the real
  implementation, so each one showed up as a duplicate result. The parser now
  skips them.
- **Test files come last.** Results from test files are listed after results
  from the rest of the code, unless the query contains the word "test". This is
  a product decision, not a measured improvement: the evaluation corpora
  exclude test directories, and queries written from library code would favour
  any rule that pushes tests down, so no metric here could fairly judge it.
- **Index built once per repository.** The in-memory index is cached and
  rebuilt when the stored chunks change (a fingerprint of chunk ids, creation
  times and source lengths is compared on each search). This also works when
  the CLI re-indexes from another process.

Default parameters: field weights name 3.0, path 1.0, docstring 1.0, body 0.25;
`k1 = 1.2`; length-normalisation `b` of 0.3 for name and path, 0.75 for
docstring and body.

## Method

### Corpora

Four third-party libraries plus RepoPilot itself, each pinned to a commit
([`corpora.json`](../backend/evaluation/corpora.json)). Indexing uses the same
`RepositoryIndexer` and AST parser as the application.

| corpus | commit | scope | split |
|---|---|---|---|
| pallets/click | `08b803c` | `src/click` | dev |
| encode/httpx | `7cff5f7` | `httpx` | dev |
| psf/requests | `3c7baaa` | `src/requests` | test |
| pallets/flask | `49943b5` | `src/flask` | test |
| RepoPilot (before this rewrite) | `6bda654` | `backend/app` | test |

The dev corpora are the only ones used to choose weights.

### Three kinds of query

1. **Hand-labelled** (18 queries on `requests`, 18 on RepoPilot's old backend).
   Written by reading the source and fixed before any ranker was run. These are
   the queries from the first version of this evaluation.
2. **Docstring queries**, in the style of CodeSearchNet (Husain et al., 2019).
   The first sentence of a function's docstring is the query and that function
   is the single relevant result. The docstring is removed from the indexed
   chunk first (field and source), so the ranker cannot match the query text
   directly. Queries shared by several functions, queries under four words,
   dunder methods and test files are dropped. This gives 110 to 195 queries
   per corpus without a query author who knows the code.
3. **Exact identifier lookup.** The query is a multi-word symbol name that is
   unique in the corpus (`parse_file`, `CaseInsensitiveDict`).

### Metrics

Recall@1, 5, 10 (equal to precision here, since each query has one relevant
chunk), MRR and nDCG@10. Confidence intervals are 95% percentile bootstrap
intervals over queries. Differences between two rankers use a paired bootstrap
on the per-query reciprocal ranks, because both rankers answer the same
queries.

### The previous ranker is kept as a baseline

[`evaluation/legacy.py`](../backend/evaluation/legacy.py) is the old scoring
code running over the same chunks. It reproduces the numbers published in the
first version of this document exactly (RepoPilot: P@1 83.3%, MRR 0.917;
requests: P@1 55.6%, MRR 0.729), which is the check that the baseline was
ported faithfully.

## Results

### Docstring queries (MRR, 95% CI)

| corpus | split | queries | previous ranker | current ranker |
|---|---|---|---|---|
| click | dev | 195 | 0.318 [0.268, 0.372] | 0.490 [0.434, 0.550] |
| httpx | dev | 110 | 0.363 [0.296, 0.430] | 0.450 [0.372, 0.528] |
| requests | test | 124 | 0.529 [0.456, 0.602] | 0.622 [0.548, 0.691] |
| flask | test | 178 | 0.420 [0.360, 0.478] | 0.548 [0.489, 0.606] |

Recall@1 on the test corpora: requests 0.387 to 0.508, flask 0.287 to 0.421.
Full tables, including R@5, R@10 and nDCG@10, are in
[`results/synthetic.md`](../backend/evaluation/results/synthetic.md).

### Hand-labelled queries

| corpus | previous: P@1 / MRR | current: P@1 / MRR |
|---|---|---|
| requests (18) | 0.556 / 0.729 | 0.833 / 0.907 |
| RepoPilot, old backend (18) | 0.833 / 0.917 | 0.833 / 0.917 |

On `requests` the two intervals overlap at 18 queries ([0.576, 0.868] against
[0.796, 1.000]), although the paired test on the same queries excludes zero
(see the ablation table). With so few queries, treat this as supporting the
docstring results, not as a result on its own. On RepoPilot's own code there is
no change at all.

### Exact identifier lookup

Both rankers return the right symbol first for every query on all five
corpora (MRR 1.000). This is a property the new ranker had to protect, not an
improvement: an earlier version of it without the exact-name rule scored 2.3
points lower MRR than the old ranker on flask identifier lookups, which is why
that rule exists.

### What each decision is worth

Change in MRR when one decision is switched off, current ranker as the
baseline. `*` marks a paired-bootstrap 95% interval that excludes zero.

| MRR | click | httpx | requests | flask | requests | flask | requests |
|---|---|---|---|---|---|---|---|
| | *docstring* | *docstring* | *docstring* | *docstring* | *identifier* | *identifier* | *hand* |
| **current ranker** | 0.490 | 0.450 | 0.622 | 0.548 | 1.000 | 1.000 | 0.907 |
| previous ranker | -0.173* | -0.087* | -0.093* | -0.128* | +0.000 | +0.000 | -0.178* |
| no identifier splitting | -0.236* | -0.150* | -0.214* | -0.324* | +0.000 | +0.000 | -0.199* |
| keep query stopwords | -0.105* | -0.101* | -0.047* | -0.116* | +0.000 | +0.000 | +0.000 |
| no stemming | -0.055* | -0.009 | -0.029 | -0.046* | +0.000 | +0.000 | -0.028 |
| no exact-name priority | +0.000 | +0.000 | +0.000 | +0.000 | -0.058* | -0.100* | +0.000 |
| class indexed by full source | +0.016 | -0.050* | -0.009 | -0.025* | +0.000 | +0.000 | +0.000 |
| per-field saturation instead of BM25F | -0.043* | -0.016 | -0.015 | -0.038* | +0.000 | +0.000 | -0.065 |
| equal field weights | -0.042* | -0.137* | -0.084* | -0.101* | +0.000 | +0.000 | -0.042 |

Reading it:

- Identifier splitting is the largest single effect, then stopword handling.
- Stemming helps on every corpus but is only clearly significant on click and
  flask.
- The class-body change is significantly better on httpx and flask, within noise
  on requests and the hand-labelled sets, and slightly worse on click (not
  significant).
- BM25F against per-field saturation: the sign favours BM25F on every column,
  significantly on click and flask. I would not claim more than "consistently a
  little better".
- Equal field weights is clearly worse, so the weights carry information.
- A fifth idea, indexing the whole identifier (`parse_file`) as an extra token,
  was tried and removed. Once the exact-name rule existed it changed nothing
  measurable, so it was not worth keeping.

### How the weights were chosen

A grid over name weight {1, 2, 3, 5}, path weight {0.25, 0.5, 1}, body weight
{0.25, 0.5, 1} was scored on the two dev corpora only
([`results/tune.md`](../backend/evaluation/results/tune.md)). The best point
(3.0, 1.0, 0.25) is the default. The top ten points lie within 0.015 MRR of each
other, the worst point is 0.10 lower. So the ranker is not sensitive to the
exact values, but it does need the name field weighted well above the body.

## Where it still fails

Examples from the hand-labelled sets:

- `"basic auth"` ranks `_basic_auth_str` above the class `HTTPBasicAuth`. The
  helper's name matches all the query words and is shorter.
- `"convert a cookiejar to a dict"` ranks `cookiejar_from_dict` (the opposite
  direction) above `dict_from_cookiejar`. A bag-of-words model has no notion of
  direction. A model that reads the phrase would be needed.
- `"write repository index to database"` ranks the exception class
  `DatabaseWriteError` above the `write` method that does the work, as it did
  before.
- `"list repositories"` and `"search repository code"` put the API route
  handler (same name, different file) above the intended service function.
  These are arguably not errors; the query does not say which one.

## Limits of this evaluation

- Each query has one relevant answer. Real searches often have several good
  results, and this metric counts the others as wrong.
- Docstring queries are not what people type. They are complete sentences
  written by the function's author, and the function's own name and code
  usually share words with them. They are used because they are objective and
  numerous; the hand-labelled sets are closer to real queries but small.
- The docstring field itself cannot be evaluated this way (its text is the
  query), so its weight (1.0) and `b` value were not tuned.
- All five corpora are well-documented, cleanly named Python libraries. Code
  with poor names or no docstrings will do worse.
- Decisions such as the stopword list, stemming and the class summary were made
  before weight tuning and were looked at on all corpora, including the test
  split. Only the three weights were tuned strictly on dev data, so the test
  split is not completely untouched.
- Hand-labelled sets have 18 queries each; their intervals are wide.

## Performance

Measured on the CPython standard library (104,961 chunks, including tests): index build 22.5 s, 1.4 GB
resident memory, 32 ms per query. A typical repository of a few thousand
chunks builds in about a second. The index lives in memory, one per
repository, with at most four cached (`INDEX_CACHE_SIZE`). Large repositories
are therefore limited by memory on small hosts, and the first search after a
restart pays the build cost.

## A published idea that did not help: pseudo-relevance feedback

Pseudo-relevance feedback assumes the top results of a first search are
relevant, adds the terms they share to the query, and searches again. Relevance
models (Lavrenko and Croft, SIGIR 2001) and their query-interpolated form
(Abdul-Jaleel et al., UMass at TREC 2004) are the usual references. It is
attractive here because code and queries often use different words, and it
needs no model and no extra hosting.

It is implemented in `SearchIndex` (off by default) and was evaluated like
everything else: a grid over feedback documents {3, 5, 10}, added terms {5, 10,
20} and weight {0.1, 0.3, 0.5}, chosen on the dev corpora only
([`results/prf.md`](../backend/evaluation/results/prf.md)). Result:

- Feedback off scores 0.4699 mean MRR on the dev corpora. The best feedback
  setting scores 0.4588, and every one of the 27 settings is below 0.4699.
- On the test corpora the best dev setting is slightly worse everywhere
  (differences of -0.014 on requests and -0.019 on flask for docstring queries;
  the flask interval only just touches zero).

So it is not used. A plausible reason is that these queries are short and the
repositories small, so the top few results are right often enough that
expansion mostly adds noise to a ranking that was already good at rank 1. I did
not test that explanation. The code stays because the result is reproducible
with `python -m evaluation.run prf`, and it may behave differently on much
larger repositories or on vaguer queries.

## Recent work on code retrieval, and why embeddings are not in yet

Dense retrievers built for code have improved quickly. CodeXEmbed (Salesforce AI
Research, COLM 2025; arXiv:2411.12644) is a family of 400M to 7B parameter models and
reports first place on CoIR. CoRNStack (Suresh et al., ICLR 2025;
arXiv:2412.01007) contributes cleaned contrastive training data and a reranker.
The jina-code-embeddings models (Kryvosheieva et al., arXiv:2508.21290,
NeurIPS 2025) reach comparable scores with 0.5B and 1.5B parameters. All of
these are the authors' own reports on benchmarks, not results on this project.

They are not integrated because:

1. They have not been evaluated here. The sandbox this work was done in could
   not download model weights, so adding one would have been untested code.
2. They need hundreds of megabytes to several gigabytes of memory, plus a
   vector store, which is the opposite of a project meant to run on a small
   free host.
3. Licences differ and need checking. At the time of writing the jina 0.5B
   model's page lists a non-commercial licence.
4. BEIR (Thakur et al., 2021) found BM25 a strong zero-shot baseline that dense
   models often fail to beat out of domain, and CoIR found that even strong
   models struggle on code retrieval tasks, so the gain is not guaranteed on
   arbitrary repositories.

The harness is built so a dense ranker is one more function with the same
signature as the current one. The plan, if you want to run it on your own
machine: embed each chunk with a model from the list above, search by cosine
similarity, fuse with the BM25F ranking using reciprocal rank fusion (Cormack
et al., SIGIR 2009), and keep it only if the paired comparison on the test
corpora shows a significant gain.

## Not done, and why

- **Qualified names for methods.** `write` alone is ambiguous; showing
  `DatabaseWriter.write` needs a schema change and a migration tool.
- **More languages.** The parser is Python's `ast`. Tree-sitter would cover
  other languages and is what cAST uses.
- **Persisted index.** The index is rebuilt in memory; storing it in
  PostgreSQL would remove the memory limit described above.

## Reproducing

From the `backend` directory, with the dependencies installed:

```bash
python -m evaluation.run fetch       # downloads the pinned commits into evaluation/.corpora
python -m evaluation.run hand        # hand-labelled queries, previous vs current
python -m evaluation.run synthetic   # docstring queries and identifier lookup
python -m evaluation.run ablate      # one decision switched off at a time
python -m evaluation.run tune        # weight grid on the dev corpora
python -m evaluation.run prf         # pseudo-relevance feedback: tuned on dev, reported on all
python -m evaluation.run -v hand     # also list the queries that were not answered at rank 1
```

Each command takes under a minute. Results written to
`backend/evaluation/results/` are the output of exactly these commands.

## References

- S. Robertson, H. Zaragoza, M. Taylor. *Simple BM25 extension to multiple
  weighted fields.* CIKM 2004. doi:10.1145/1031171.1031181
- S. Robertson, H. Zaragoza. *The Probabilistic Relevance Framework: BM25 and
  Beyond.* Foundations and Trends in Information Retrieval 3(4), 2009.
  doi:10.1561/1500000019
- C. Kamphuis, A. de Vries, L. Boytsov, J. Lin. *Which BM25 Do You Mean? A
  Large-Scale Reproducibility Study of Scoring Variants.* ECIR 2020.
- H. Husain, H.-H. Wu, T. Gazit, M. Allamanis, M. Brockschmidt.
  *CodeSearchNet Challenge: Evaluating the State of Semantic Code Search.*
  arXiv:1909.09436, 2019.
- Y. Zhang, X. Zhao, Z. Z. Wang, C. Yang, J. Wei, T. Wu. *cAST: Enhancing Code
  Retrieval-Augmented Generation with Structural Chunking via Abstract Syntax
  Tree.* arXiv:2506.15655, 2025.
- N. Thakur, N. Reimers, A. Rücklé, A. Srivastava, I. Gurevych. *BEIR: A
  Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval
  Models.* NeurIPS Datasets and Benchmarks, 2021. arXiv:2104.08663
- X. Li et al. *CoIR: A Comprehensive Benchmark for Code Information Retrieval
  Models.* arXiv:2407.02883, 2024.
- V. Lavrenko, W. B. Croft. *Relevance-Based Language Models.* SIGIR 2001, pp.
  120-127. doi:10.1145/383952.383972
- N. Abdul-Jaleel et al. *UMass at TREC 2004: Novelty and HARD.* TREC 2004.
- Salesforce AI Research. *CodeXEmbed: A Generalist Embedding Model Family for
  Multilingual and Multi-task Code Retrieval.* COLM 2025. arXiv:2411.12644
- T. Suresh, R. Gangi Reddy, Y. Xu, Z. Nussbaum, A. Mulyar, B. Duderstadt, H.
  Ji. *CoRNStack: High-Quality Contrastive Data for Better Code Retrieval and
  Reranking.* ICLR 2025. arXiv:2412.01007
- D. Kryvosheieva, S. Sturua, M. Günther, S. Martens, H. Xiao. *Efficient Code
  Embeddings from Code Generation Models.* NeurIPS 2025. arXiv:2508.21290
- G. Cormack, C. Clarke, S. Büttcher. *Reciprocal Rank Fusion outperforms
  Condorcet and individual rank learning methods.* SIGIR 2009.
  doi:10.1145/1571941.1572114
