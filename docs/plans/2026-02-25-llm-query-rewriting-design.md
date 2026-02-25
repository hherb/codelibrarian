# LLM-Powered Query Rewriting & Focus-Based Score Adjustment

**Date:** 2026-02-25
**Status:** Approved

## Problem

Natural language queries like "how are edges inserted into the graph?" produce poor
search results. The hybrid search pipeline strips stop words and searches for
`"edges" "inserted" "graph"`, which matches test files and tangentially related
symbols rather than the actual implementation code (`store_parse_result`,
`INSERT INTO calls/imports/inherits`).

Two distinct issues:
1. **Query terms don't match code vocabulary** — natural language needs translation
   into function names, SQL keywords, variable names, etc.
2. **Test files rank equally with implementation** — when the user asks about how
   code works, test fixtures and test helpers shouldn't dominate results.

## Solution

Add an LLM-powered query rewrite layer that translates natural language into
code-aware search terms, plus a focus-based score multiplier that adjusts ranking
based on whether the user is asking about implementation, tests, or both.

Uses a small local model (`qwen2.5:3b`) via Ollama, invoked only when needed.

## Architecture

### Data Flow

```
search(query, rewrite=False)
  → _classify_intent(query)              # existing: graph routing (unchanged)
  → if graph intent matched: dispatch     # unchanged
  → if rewrite=True:
       → QueryRewriter.rewrite(query)     # forced LLM rewrite
       → search with rewritten terms + apply focus multiplier
  → elif _should_rewrite(query):
       → QueryRewriter.rewrite(query)     # heuristic-triggered LLM rewrite
       → search with rewritten terms + apply focus multiplier
  → else:
       → run hybrid search with original query
       → if zero results:
            → QueryRewriter.rewrite(query) # fallback LLM rewrite
            → search with rewritten terms + apply focus multiplier
```

Key principle: the LLM is in the hot path only when needed, and any failure
falls back gracefully to the existing pipeline.

### New Components

| Component | File | Role |
|-----------|------|------|
| `QueryRewriter` | `src/codelibrarian/query_rewriter.py` | Calls Ollama chat completions, parses JSON response |
| `_should_rewrite()` | `src/codelibrarian/searcher.py` | Heuristic: skip LLM if query is code-like |
| `_apply_focus()` | `src/codelibrarian/searcher.py` | Multiplies scores based on focus + file path |
| `_is_test_file()` | `src/codelibrarian/searcher.py` | Detects test files by path convention |
| `RewrittenQuery` | `src/codelibrarian/models.py` | Dataclass: `terms: list[str]`, `focus: str` |
| Config section | `src/codelibrarian/config.py` | `[query_rewrite]` with enabled/api_url/model/timeout |

### What Doesn't Change

- Graph intent routing (regex-based, runs first)
- The hybrid search algorithm itself (FTS + vector merge)
- Embedding client
- CLI commands other than `search`
- Existing MCP tools (graph tools, lookup, list_symbols, diagrams)

## The `_should_rewrite()` Heuristic

Fast, no-I/O function that decides whether to invoke the LLM.

**Skip LLM (return False) when:**
1. Query contains dots suggesting qualified names (`store.insert_call`)
2. Query tokens are camelCase or snake_case (`insertCall`, `insert_call`)
3. Query has fewer than 3 tokens after stop-word removal (too short — probably a
   keyword search like `"graph edges"`)
4. Query rewriting is disabled in config

**Invoke LLM (return True) when:**
1. Query contains question words (`how`, `what`, `where`, `why`) combined with 3+
   non-stop-word tokens
2. Query has high stop-word ratio (>40% of tokens are stop words — signals natural
   language)
3. Multiple tokens but none match any obvious code patterns

## The `QueryRewriter` Client

### Prompt Design

The system prompt is vocabulary-aware: `Searcher` fetches the codebase's symbol
names via `SQLiteStore.get_symbol_vocabulary()` and passes them to the rewriter.
This lets the 3B model pick actual identifiers (like `insert_call`,
`resolve_graph_edges`) instead of generic words (like `insert`, `graph`).

```
You are a code search assistant. Given a natural language question about a codebase,
return JSON with search terms a developer would use to find the relevant code.

Available symbols in the codebase:
Animal, AnimalShelter, BaseParser, ..., insert_call, insert_import, ...

Return ONLY valid JSON:
{"terms": ["term1", "term2", ...], "focus": "implementation"|"tests"|"all"}

Rules:
- terms: 3-6 search terms, preferring actual symbol names from the codebase
- focus: "implementation" if asking about how code works, "tests" if asking about testing, "all" if unclear
- No explanations, just JSON
```

The vocabulary is cached on the `Searcher` instance (lazy-loaded once per session).
Without vocabulary the prompt still works, just with less precise terms.

User message is the raw query string.

### Class Interface

```python
class QueryRewriter:
    def __init__(self, api_url: str, model: str, timeout: float = 5.0): ...

    def rewrite(self, query: str, vocabulary: list[str] | None = None) -> RewrittenQuery | None:
        """Call LLM to rewrite query. Returns None on any failure."""
        ...

    def close(self): ...
    def __enter__(self): ...
    def __exit__(self, *_): ...
```

Returns `None` on timeout, connection error, or unparseable JSON. Search falls
back to the original query in all failure cases.

### RewrittenQuery Dataclass

```python
@dataclass
class RewrittenQuery:
    terms: list[str]       # 3-6 code-aware search terms
    focus: str             # "implementation", "tests", "all"
```

### How Rewritten Terms Feed Into Search

Rewritten terms are searched with **OR mode** in FTS (each term is an independent
symbol suggestion, not a conjunctive phrase). The results are **merged** with a
parallel search using the original query:

1. Search rewritten terms (OR mode FTS + embedding)
2. Search original query (AND mode FTS + embedding, as before)
3. Merge results: for duplicates, keep the higher score
4. Apply focus multiplier
5. Truncate to requested limit

This dual-search approach ensures the LLM's code-vocabulary suggestions AND the
original semantic match both contribute. The merge uses `limit * 3` candidates
internally so focus adjustment has room to re-rank before truncation.

## Focus-Based Score Adjustment

After hybrid search produces scored results, the `focus` value applies a multiplier:

- `focus="implementation"`: test file scores × 0.5
- `focus="tests"`: implementation file scores × 0.5
- `focus="all"`: no adjustment (default, and fallback if LLM skipped)

`_is_test_file(path)` checks: path contains `tests/` or filename starts with
`test_` or ends with `_test.py`. Standard Python conventions, extensible later.

The 0.5 multiplier means test results can still appear — they just need to score
2× higher than implementation results to rank above them.

## Configuration

New section in `config.toml`:

```toml
[query_rewrite]
enabled    = true
api_url    = "http://localhost:11434/v1/chat/completions"
model      = "qwen2.5:3b"
timeout    = 5.0
```

Config properties: `query_rewrite_enabled`, `query_rewrite_api_url`,
`query_rewrite_model`, `query_rewrite_timeout`.

If `enabled = false`, the LLM is never called — even with `--rewrite`. The flag
silently becomes a no-op.

Default config includes `[query_rewrite]` so new users get it out of the box.

## Interface Changes

### CLI (`search` command)

Add `--rewrite / -r` flag:

```bash
codelibrarian search "how are edges inserted into the graph?" --rewrite
```

### MCP (`search_code` tool)

Add `rewrite` parameter to inputSchema:

```json
{
  "rewrite": {
    "type": "boolean",
    "default": false,
    "description": "Force LLM-based query rewriting for better natural language understanding"
  }
}
```

### Searcher

```python
class Searcher:
    def __init__(self, store, embedder=None, rewriter=None): ...

    def search(self, query, limit=10, semantic_only=False, text_only=False,
               rewrite=False) -> list[SearchResult]: ...
```

CLI and MCP server construct `QueryRewriter` from config and pass it to
`Searcher.__init__`, same pattern as `EmbeddingClient`.

## Testing Strategy

- **Unit tests for `_should_rewrite()`** — pure function, no mocking. Cover
  code-like queries, natural language queries, edge cases.
- **Unit tests for `QueryRewriter.rewrite()`** — mock httpx, verify JSON parsing
  and graceful failure on timeout/bad JSON/connection error.
- **Unit tests for `_apply_focus()`** — verify score adjustment for
  implementation/tests/all focus values.
- **Unit tests for `_is_test_file()`** — various path patterns.
- **Integration test** — mock LLM response, verify `search(rewrite=True)` produces
  different results than raw query.
- **No live Ollama in CI** — all LLM calls mocked. Manual test script for local
  verification.

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM model | qwen2.5:3b via Ollama | Already pulled, <=3B spec, good instruction following |
| When to invoke LLM | Heuristic + force flag + zero-results fallback | Keeps most queries fast, covers all cases |
| Query rewrite format | JSON with terms + focus | Structured, parseable by small model |
| Score adjustment | 0.7x multiplier on out-of-focus files | Mild enough to not hide relevant results |
| Failure handling | Return None, fall back to original query | LLM is advisory, never blocks search |
| Config | Separate `[query_rewrite]` section | Independent from embeddings, different endpoint/model possible |
