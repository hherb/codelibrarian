"""Searcher: all query types over the indexed codebase."""

from __future__ import annotations

import re

from codelibrarian.embeddings import EmbeddingClient
from codelibrarian.models import SearchResult, SymbolRecord
from codelibrarian.storage.store import SQLiteStore

# BM25 scores are negative; dividing by this scale brings typical values into [0, 1].
# Empirically, absolute BM25 scores for short documents rarely exceed this value.
_BM25_SCALE: float = 10.0


class Searcher:
    def __init__(self, store: SQLiteStore, embedder: EmbeddingClient | None = None):
        self.store = store
        self.embedder = embedder

    # ------------------------------------------------------------------ #
    # Hybrid search (primary entry point)
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        limit: int = 10,
        semantic_only: bool = False,
        text_only: bool = False,
    ) -> list[SearchResult]:
        # --- Graph intent routing ---
        intent = _classify_intent(query)
        if intent is not None:
            intent_type, symbol_name = intent
            result = self._dispatch_graph(intent_type, symbol_name, limit)
            if result is not None:
                return result
        # --- Existing hybrid search (unchanged below this point) ---
        fts_hits: dict[int, float] = {}
        vec_hits: dict[int, float] = {}

        if not text_only and self.embedder:
            query_vec = self.embedder.embed_one(query)
            if query_vec:
                for sym_id, dist in self.store.vector_search(query_vec, limit=limit * 2):
                    # Cosine distance ranges from 0 (identical) to 2 (opposite).
                    # Convert to a 0-1 similarity score.
                    vec_hits[sym_id] = max(0.0, 1.0 - dist / 2.0)

        if not semantic_only:
            safe_query = _fts5_query(query)
            if safe_query:
                for sym_id, score in self.store.fts_search(safe_query, limit=limit * 2):
                    fts_hits[sym_id] = min(score / _BM25_SCALE, 1.0)
            # If AND matched nothing, fall back to OR so partial matches surface
            if not fts_hits:
                or_query = _fts5_query(query, use_or=True)
                if or_query and or_query != safe_query:
                    for sym_id, score in self.store.fts_search(or_query, limit=limit * 2):
                        fts_hits[sym_id] = min(score / _BM25_SCALE, 1.0)

        # Merge scores
        all_ids = set(fts_hits) | set(vec_hits)
        scored: list[tuple[int, float, str]] = []
        for sym_id in all_ids:
            fts_score = fts_hits.get(sym_id, 0.0)
            vec_score = vec_hits.get(sym_id, 0.0)
            n_sources = (1 if fts_score > 0 else 0) + (1 if vec_score > 0 else 0)
            if n_sources == 0:
                continue
            combined = (fts_score + vec_score) / n_sources
            if fts_score > 0 and vec_score > 0:
                match_type = "hybrid"
            elif fts_score > 0:
                match_type = "fulltext"
            else:
                match_type = "semantic"
            scored.append((sym_id, combined, match_type))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for sym_id, score, match_type in scored[:limit]:
            sym = self.store.get_symbol_by_id(sym_id)
            if sym:
                results.append(SearchResult(symbol=sym, score=score, match_type=match_type))
        return results

    # ------------------------------------------------------------------ #
    # Symbol lookup
    # ------------------------------------------------------------------ #

    def lookup_symbol(self, name: str) -> list[SymbolRecord]:
        exact = self.store.lookup_symbol(name)
        if exact:
            return exact
        return self.store.lookup_symbol_prefix(name)

    # ------------------------------------------------------------------ #
    # Navigation queries
    # ------------------------------------------------------------------ #

    def get_callers(self, qualified_name: str, depth: int = 1) -> list[SymbolRecord]:
        return self.store.get_callers(qualified_name, depth)

    def get_callees(self, qualified_name: str, depth: int = 1) -> list[SymbolRecord]:
        return self.store.get_callees(qualified_name, depth)

    def get_file_imports(self, file_path: str) -> dict:
        return self.store.get_file_imports(file_path)

    # ------------------------------------------------------------------ #
    # Structural queries
    # ------------------------------------------------------------------ #

    def list_symbols(
        self,
        kind: str | None = None,
        pattern: str | None = None,
        file_path: str | None = None,
    ) -> list[SymbolRecord]:
        return self.store.list_symbols(kind=kind, pattern=pattern, file_path=file_path)

    def get_class_hierarchy(self, class_name: str) -> dict:
        return self.store.get_class_hierarchy(class_name)

    # ------------------------------------------------------------------ #
    # Graph dispatch (internal)
    # ------------------------------------------------------------------ #

    def _dispatch_graph(
        self, intent: str, symbol_name: str, limit: int
    ) -> list[SearchResult] | None:
        """Dispatch to a graph query. Returns None if the symbol isn't found."""
        if intent == "callers":
            if not self.store.lookup_symbol(symbol_name):
                return None
            symbols = self.get_callers(symbol_name)
            return [
                SearchResult(symbol=s, score=1.0, match_type="graph")
                for s in symbols[:limit]
            ]
        elif intent == "callees":
            if not self.store.lookup_symbol(symbol_name):
                return None
            symbols = self.get_callees(symbol_name)
            return [
                SearchResult(symbol=s, score=1.0, match_type="graph")
                for s in symbols[:limit]
            ]
        elif intent == "hierarchy":
            hierarchy = self.get_class_hierarchy(symbol_name)
            if hierarchy.get("class") is None:
                return None
            results = []
            for entry in hierarchy.get("parents", []):
                sym = self.store.lookup_symbol(entry["qualified_name"])
                if sym:
                    results.append(
                        SearchResult(symbol=sym[0], score=1.0, match_type="graph")
                    )
            for entry in hierarchy.get("children", []):
                sym = self.store.lookup_symbol(entry["qualified_name"])
                if sym:
                    results.append(
                        SearchResult(symbol=sym[0], score=1.0, match_type="graph")
                    )
            return results[:limit] if results else None
        return None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "has", "have", "had", "having",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it", "its",
    "they", "them", "their", "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "about", "between", "through", "during", "above", "below",
    "and", "or", "but", "not", "nor", "so", "yet",
    "if", "then", "else", "when", "where", "how", "what", "which", "who",
    "whom", "why", "all", "each", "every", "both", "few", "more", "most",
    "some", "any", "no", "only", "very", "can", "will", "just",
})


def _fts5_query(query: str, *, use_or: bool = False) -> str:
    """Convert a natural-language query into safe FTS5 search tokens.

    Strips punctuation, removes stop words, and quotes each remaining token
    individually.  By default tokens are joined with implicit AND; pass
    *use_or=True* to join with OR so that partial matches are returned.
    """
    stripped = query.strip()
    if not stripped:
        return ""
    tokens = re.split(r"[^\w]+", stripped)
    # Remove stop words and empty tokens
    tokens = [t for t in tokens if t and t.lower() not in _STOP_WORDS]
    if not tokens:
        # All tokens were stop words; fall back to the original minus punctuation
        fallback = re.sub(r"[^\w\s]+", "", stripped)
        if not fallback.strip():
            return ""
        escaped = fallback.replace('"', '""')
        return f'"{escaped}"'
    quoted = [f'"{t}"' for t in tokens]
    if use_or and len(quoted) > 1:
        return " OR ".join(quoted)
    return " ".join(quoted)


# --------------------------------------------------------------------------- #
# Intent classification
# --------------------------------------------------------------------------- #

# Each tuple: (compiled regex, intent name, group index for symbol name).
# Patterns are tried in order; first match wins.
_INTENT_PATTERNS: list[tuple[re.Pattern, str, int]] = [
    # -- callees --
    (re.compile(r"(?:what|which\s+\w+)\s+(?:does|did)\s+([\w.]+)\s+call", re.I), "callees", 1),
    (re.compile(r"(?:functions?|methods?|symbols?)?\s*called\s+by\s+([\w.]+)", re.I), "callees", 1),
    (re.compile(r"callees?\s+(?:of|for)\s+([\w.]+)", re.I), "callees", 1),
    (re.compile(r"([\w.]+)\s+calls\s+what", re.I), "callees", 1),
    (re.compile(r"dependencies\s+of\s+([\w.]+)", re.I), "callees", 1),
    # -- callers --
    (re.compile(r"(?:who|what)\s+calls?\s+([\w.]+)", re.I), "callers", 1),
    (re.compile(r"callers?\s+(?:of|for)\s+([\w.]+)", re.I), "callers", 1),
    (re.compile(r"where\s+is\s+([\w.]+)\s+(?:used|called|invoked)", re.I), "callers", 1),
    (re.compile(r"usages?\s+of\s+([\w.]+)", re.I), "callers", 1),
    # -- hierarchy --
    (re.compile(r"subclass(?:es)?\s+of\s+([\w.]+)", re.I), "hierarchy", 1),
    (re.compile(r"([\w.]+)\s+inherits?\s+from", re.I), "hierarchy", 1),
    (re.compile(r"parent\s+class(?:es)?\s+of\s+([\w.]+)", re.I), "hierarchy", 1),
    (re.compile(r"children\s+of\s+([\w.]+)", re.I), "hierarchy", 1),
    (re.compile(r"(?:super|base)\s*class(?:es)?\s+of\s+([\w.]+)", re.I), "hierarchy", 1),
]


def _classify_intent(query: str) -> tuple[str, str] | None:
    """Classify a natural-language query as a graph intent.

    Returns (intent, symbol_name) if a graph pattern matches, None otherwise.
    Intent is one of: "callers", "callees", "hierarchy".
    """
    query = query.strip()
    if not query:
        return None
    for pattern, intent, group_idx in _INTENT_PATTERNS:
        m = pattern.search(query)
        if m:
            return (intent, m.group(group_idx))
    return None
