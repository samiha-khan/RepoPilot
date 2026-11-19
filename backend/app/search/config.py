from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    """Ranking parameters.

    Field weights scale the term frequency of each field before BM25
    saturation (BM25F, Robertson et al. 2004). ``b`` is length
    normalisation, applied per field. The flags exist so the evaluation
    harness can switch one design decision off at a time.
    """

    weight_name: float = 3.0
    weight_path: float = 1.0
    weight_docstring: float = 1.0
    weight_body: float = 0.25

    b_name: float = 0.3
    b_path: float = 0.3
    b_docstring: float = 0.75
    b_body: float = 0.75

    k1: float = 1.2

    # "bm25f": weighted term frequencies are summed across fields and then
    # saturated once (the BM25F recommendation). "linear": each field is
    # saturated on its own and the weighted results are summed, which is how
    # the previous ranker combined fields.
    combine: str = "bm25f"

    # Index identifiers as sub-tokens (parse_file -> parse, file).
    split_identifiers: bool = True
    # Reduce words to stems (parsing, parsed -> pars) with the Snowball stemmer.
    stem: bool = True
    # Drop English function words from queries ("a", "the", "for", ...).
    drop_query_stopwords: bool = True
    # A symbol whose name equals the query (ignoring case) is ranked above
    # every other result; BM25F decides the order within each group.
    exact_symbol_first: bool = True
    # "summary": a class is indexed by its own header, docstring, class-level
    # statements and method names, not by the bodies of its methods (those are
    # separate chunks). "full": index the whole class source.
    class_body: str = "summary"


DEFAULT_CONFIG = SearchConfig()
