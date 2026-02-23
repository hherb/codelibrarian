"""Searcher: all query types over the indexed codebase."""

from __future__ import annotations

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
        fts_hits: dict[int, float] = {}
        vec_hits: dict[int, float] = {}

        if not text_only and self.embedder:
            query_vec = self.embedder.embed_one(query)
            if query_vec:
                for sym_id, dist in self.store.vector_search(query_vec, limit=limit * 2):
                    # Convert distance to a 0-1 similarity score
                    vec_hits[sym_id] = max(0.0, 1.0 - dist)

        if not semantic_only:
            # Escape FTS5 special characters
            safe_query = _escape_fts5(query)
            if safe_query:
                for sym_id, score in self.store.fts_search(safe_query, limit=limit * 2):
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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _escape_fts5(query: str) -> str:
    """Escape FTS5 special characters; fall back to quoted phrase if needed."""
    # Remove characters that can't be easily escaped in FTS5
    stripped = query.strip()
    if not stripped:
        return ""
    # If the query has special FTS5 operators, wrap in quotes for phrase search
    special = set('"-*()^')
    if any(c in stripped for c in special):
        escaped = stripped.replace('"', '""')
        return f'"{escaped}"'
    return stripped
