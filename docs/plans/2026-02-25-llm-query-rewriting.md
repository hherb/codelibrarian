# LLM Query Rewriting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LLM-powered query rewriting so natural language searches like "how are edges inserted into the graph?" produce code-relevant results, with focus-based score adjustment to rank implementation vs test files appropriately.

**Architecture:** A `QueryRewriter` client calls a local Ollama model (qwen2.5:3b) to translate natural language into code search terms + a focus signal. A `_should_rewrite()` heuristic gates the LLM call; `--rewrite` flag forces it; zero-result fallback triggers it automatically. Focus-based score multipliers adjust ranking post-search.

**Tech Stack:** Python httpx (already a dependency), Ollama chat completions API, qwen2.5:3b model

---

### Task 1: Add `RewrittenQuery` dataclass to models

**Files:**
- Modify: `src/codelibrarian/models.py:148-158`
- Test: `tests/test_models.py` (if it exists, otherwise inline verification)

**Step 1: Write the dataclass**

Add to `src/codelibrarian/models.py`, after the `ParseResult` class (line 76) and before `FileRecord` (line 79):

```python
@dataclass
class RewrittenQuery:
    """Result of LLM-based query rewriting."""

    terms: list[str]
    focus: str = "all"  # "implementation", "tests", "all"
```

**Step 2: Run existing tests to confirm nothing breaks**

Run: `pytest tests/ -v`
Expected: All existing tests pass (additive change only).

**Step 3: Commit**

```bash
git add src/codelibrarian/models.py
git commit -m "feat: add RewrittenQuery dataclass to models"
```

---

### Task 2: Add `[query_rewrite]` config section

**Files:**
- Modify: `src/codelibrarian/config.py:18-45` (DEFAULT_CONFIG)
- Modify: `src/codelibrarian/config.py:69-154` (Config class)
- Modify: `src/codelibrarian/config.py:178-202` (DEFAULT_CONFIG_TOML)

**Step 1: Add defaults to DEFAULT_CONFIG dict**

In `src/codelibrarian/config.py`, add after the `"database"` entry in `DEFAULT_CONFIG` (after line 44):

```python
    "query_rewrite": {
        "enabled": True,
        "api_url": "http://localhost:11434/v1/chat/completions",
        "model": "qwen2.5:3b",
        "timeout": 5.0,
    },
```

**Step 2: Add Config properties**

In `src/codelibrarian/config.py`, add after the `db_path` property (after line 138):

```python
    # --- query rewrite ---
    @property
    def query_rewrite_enabled(self) -> bool:
        return self._data.get("query_rewrite", {}).get("enabled", True)

    @property
    def query_rewrite_api_url(self) -> str:
        return self._data.get("query_rewrite", {}).get(
            "api_url", "http://localhost:11434/v1/chat/completions"
        )

    @property
    def query_rewrite_model(self) -> str:
        return self._data.get("query_rewrite", {}).get("model", "qwen2.5:3b")

    @property
    def query_rewrite_timeout(self) -> float:
        return self._data.get("query_rewrite", {}).get("timeout", 5.0)
```

**Step 3: Add to DEFAULT_CONFIG_TOML string**

In `src/codelibrarian/config.py`, add before the closing `"""` of `DEFAULT_CONFIG_TOML` (before line 202):

```toml

[query_rewrite]
enabled = true
api_url = "http://localhost:11434/v1/chat/completions"
model   = "qwen2.5:3b"
timeout = 5.0
```

**Step 4: Run existing tests**

Run: `pytest tests/ -v`
Expected: All pass. Existing Config test fixtures don't include `query_rewrite` key, so the `.get()` fallbacks handle it.

**Step 5: Commit**

```bash
git add src/codelibrarian/config.py
git commit -m "feat: add [query_rewrite] config section"
```

---

### Task 3: Create `QueryRewriter` client with tests

**Files:**
- Create: `src/codelibrarian/query_rewriter.py`
- Create: `tests/test_query_rewriter.py`

**Step 1: Write failing tests**

Create `tests/test_query_rewriter.py`:

```python
"""Tests for QueryRewriter — all LLM calls are mocked."""

import json
from unittest.mock import MagicMock, patch

import pytest

from codelibrarian.models import RewrittenQuery
from codelibrarian.query_rewriter import QueryRewriter


@pytest.fixture
def rewriter():
    return QueryRewriter(
        api_url="http://localhost:11434/v1/chat/completions",
        model="qwen2.5:3b",
        timeout=5.0,
    )


class TestRewrite:
    def test_parses_valid_json_response(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "terms": ["insert_call", "INSERT INTO", "store_parse_result"],
                                "focus": "implementation",
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("how are edges inserted into the graph?")

        assert result is not None
        assert result.terms == ["insert_call", "INSERT INTO", "store_parse_result"]
        assert result.focus == "implementation"

    def test_returns_none_on_timeout(self, rewriter):
        import httpx

        with patch.object(
            rewriter._client, "post", side_effect=httpx.TimeoutException("timeout")
        ):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_returns_none_on_connection_error(self, rewriter):
        import httpx

        with patch.object(
            rewriter._client, "post", side_effect=httpx.ConnectError("refused")
        ):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_returns_none_on_invalid_json(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json at all"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_returns_none_on_missing_terms(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps({"focus": "implementation"})}}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("some query")

        assert result is None

    def test_defaults_focus_to_all(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"terms": ["find_oldest", "animal"]}
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("find oldest animal")

        assert result is not None
        assert result.focus == "all"

    def test_strips_markdown_fences_from_response(self, rewriter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"terms": ["foo", "bar"], "focus": "all"}\n```'
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(rewriter._client, "post", return_value=mock_response):
            result = rewriter.rewrite("some query")

        assert result is not None
        assert result.terms == ["foo", "bar"]


class TestContextManager:
    def test_enters_and_exits(self):
        rw = QueryRewriter(
            api_url="http://localhost:11434/v1/chat/completions",
            model="qwen2.5:3b",
        )
        with rw as r:
            assert r is rw
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_query_rewriter.py -v`
Expected: FAIL — `query_rewriter` module doesn't exist yet.

**Step 3: Implement QueryRewriter**

Create `src/codelibrarian/query_rewriter.py`:

```python
"""LLM-powered query rewriter using an OpenAI-compatible chat completions API."""

from __future__ import annotations

import json
import logging
import re

import httpx

from codelibrarian.models import RewrittenQuery

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a code search assistant. Given a natural language question about a codebase, \
return JSON with search terms a developer would use to find the relevant code.

Return ONLY valid JSON:
{"terms": ["term1", "term2", ...], "focus": "implementation"|"tests"|"all"}

Rules:
- terms: 3-6 short search terms (function names, variable names, SQL keywords, etc.)
- focus: "implementation" if asking about how code works, "tests" if asking about testing, "all" if unclear
- No explanations, just JSON"""


class QueryRewriter:
    def __init__(
        self,
        api_url: str,
        model: str,
        timeout: float = 5.0,
    ):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout)

    def rewrite(self, query: str) -> RewrittenQuery | None:
        """Rewrite a natural language query into code search terms.

        Returns None on any failure (timeout, connection error, bad JSON).
        """
        try:
            resp = self._client.post(
                self.api_url,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content)
        except Exception as exc:
            logger.debug("Query rewrite failed: %s", exc)
            return None

    def _parse_response(self, content: str) -> RewrittenQuery | None:
        """Parse the LLM response into a RewrittenQuery."""
        # Strip markdown code fences if present
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("Query rewrite returned invalid JSON: %s", content)
            return None

        terms = parsed.get("terms")
        if not terms or not isinstance(terms, list):
            return None

        focus = parsed.get("focus", "all")
        if focus not in ("implementation", "tests", "all"):
            focus = "all"

        return RewrittenQuery(terms=terms, focus=focus)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "QueryRewriter":
        return self

    def __exit__(self, *_) -> None:
        self.close()
```

**Step 4: Run tests**

Run: `pytest tests/test_query_rewriter.py -v`
Expected: All PASS.

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add src/codelibrarian/query_rewriter.py tests/test_query_rewriter.py
git commit -m "feat: add QueryRewriter client with mocked tests"
```

---

### Task 4: Add `_should_rewrite()`, `_is_test_file()`, and `_apply_focus()` to searcher with tests

**Files:**
- Modify: `src/codelibrarian/searcher.py`
- Modify: `tests/test_searcher.py`

**Step 1: Write failing tests**

Add to the bottom of `tests/test_searcher.py`:

```python
from codelibrarian.searcher import _should_rewrite, _is_test_file


class TestShouldRewrite:
    """Tests for the rewrite heuristic."""

    def test_natural_language_question(self):
        assert _should_rewrite("how are edges inserted into the graph?") is True

    def test_question_with_what(self):
        assert _should_rewrite("what function handles authentication") is True

    def test_question_with_where(self):
        assert _should_rewrite("where does the config file get loaded") is True

    def test_high_stop_word_ratio(self):
        assert _should_rewrite("how does the system handle errors in the pipeline") is True

    def test_code_like_snake_case(self):
        assert _should_rewrite("insert_call") is False

    def test_code_like_camel_case(self):
        assert _should_rewrite("insertCall") is False

    def test_code_like_dotted_path(self):
        assert _should_rewrite("store.insert_call") is False

    def test_short_keyword_query(self):
        assert _should_rewrite("graph edges") is False

    def test_single_word(self):
        assert _should_rewrite("search") is False

    def test_empty_string(self):
        assert _should_rewrite("") is False


class TestIsTestFile:
    def test_tests_directory(self):
        assert _is_test_file("tests/test_store.py") is True

    def test_test_prefix(self):
        assert _is_test_file("src/test_helper.py") is True

    def test_test_suffix(self):
        assert _is_test_file("src/store_test.py") is True

    def test_implementation_file(self):
        assert _is_test_file("src/codelibrarian/store.py") is False

    def test_nested_tests_dir(self):
        assert _is_test_file("project/tests/unit/test_foo.py") is True

    def test_fixture_file(self):
        assert _is_test_file("tests/fixtures/sample.py") is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_searcher.py::TestShouldRewrite -v`
Expected: FAIL — `_should_rewrite` doesn't exist.

**Step 3: Implement the helper functions**

Add to `src/codelibrarian/searcher.py`, after the `_classify_intent` function (after line 254):

```python
# --------------------------------------------------------------------------- #
# Query rewrite heuristic
# --------------------------------------------------------------------------- #

_QUESTION_WORDS = frozenset({"how", "what", "where", "why", "when", "which", "does", "do"})

_CAMEL_CASE_RE = re.compile(r"[a-z][A-Z]")
_SNAKE_CASE_RE = re.compile(r"\w+_\w+")
_DOTTED_PATH_RE = re.compile(r"\w+\.\w+")


def _should_rewrite(query: str) -> bool:
    """Decide whether a query needs LLM rewriting.

    Returns True for natural-language queries, False for code-like queries.
    """
    query = query.strip()
    if not query:
        return False

    # Code-like patterns: skip LLM
    if _DOTTED_PATH_RE.search(query):
        return False
    if _CAMEL_CASE_RE.search(query):
        return False

    tokens = re.split(r"[^\w]+", query)
    tokens = [t for t in tokens if t]
    if not tokens:
        return False

    # Single snake_case token: code-like
    if len(tokens) == 1 and _SNAKE_CASE_RE.match(tokens[0]):
        return False

    non_stop = [t for t in tokens if t.lower() not in _STOP_WORDS]

    # Too few meaningful tokens: probably a keyword search
    if len(non_stop) < 3:
        # Unless any remaining token is snake_case
        if any(_SNAKE_CASE_RE.match(t) for t in non_stop):
            return False
        # Short queries without code patterns — still not enough signal
        return False

    # Any token is snake_case: code-like
    if any(_SNAKE_CASE_RE.match(t) for t in tokens):
        return False

    # Contains question words + enough tokens: natural language
    lower_tokens = {t.lower() for t in tokens}
    if lower_tokens & _QUESTION_WORDS:
        return True

    # High stop-word ratio signals natural language
    stop_count = sum(1 for t in tokens if t.lower() in _STOP_WORDS)
    if len(tokens) > 0 and stop_count / len(tokens) > 0.4:
        return True

    return False


# --------------------------------------------------------------------------- #
# Focus-based score adjustment
# --------------------------------------------------------------------------- #


def _is_test_file(path: str) -> bool:
    """Check if a file path looks like a test file."""
    import os

    parts = path.replace("\\", "/").split("/")
    basename = os.path.basename(path)
    # Path contains tests/ directory
    if "tests" in parts:
        return True
    # File starts with test_ or ends with _test.py
    if basename.startswith("test_") or basename.endswith("_test.py"):
        return True
    return False
```

**Step 4: Run tests**

Run: `pytest tests/test_searcher.py::TestShouldRewrite tests/test_searcher.py::TestIsTestFile -v`
Expected: All PASS.

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add src/codelibrarian/searcher.py tests/test_searcher.py
git commit -m "feat: add _should_rewrite() heuristic and _is_test_file() helper"
```

---

### Task 5: Wire query rewriting into `Searcher.search()`

**Files:**
- Modify: `src/codelibrarian/searcher.py:16-87` (Searcher class)
- Modify: `tests/test_searcher.py`

**Step 1: Write failing tests**

Add to the bottom of `tests/test_searcher.py`:

```python
import json
from unittest.mock import MagicMock, patch

from codelibrarian.models import RewrittenQuery
from codelibrarian.query_rewriter import QueryRewriter


@pytest.fixture
def searcher_with_rewriter(tmp_path):
    """Searcher with a mocked QueryRewriter."""
    config_dir = tmp_path / ".codelibrarian"
    config_dir.mkdir()

    config = Config(
        data={
            "index": {
                "root": str(FIXTURES),
                "exclude": ["__pycache__/", ".git/"],
                "languages": ["python"],
            },
            "embeddings": {
                "api_url": "http://localhost:11434/v1/embeddings",
                "model": "nomic-embed-text-v2-moe",
                "dimensions": 4,
                "batch_size": 32,
                "max_chars": 1600,
                "enabled": False,
            },
            "database": {"path": str(tmp_path / "test.db")},
        },
        config_dir=config_dir,
    )

    store = SQLiteStore(config.db_path, embedding_dimensions=4)
    store.connect()
    store.init_schema()

    indexer = Indexer(store, config)
    indexer.index_root()
    store.conn.commit()

    rewriter = MagicMock(spec=QueryRewriter)
    yield Searcher(store, embedder=None, rewriter=rewriter), rewriter

    store.close()


def test_search_with_forced_rewrite(searcher_with_rewriter):
    """rewrite=True should call the rewriter and use rewritten terms."""
    s, mock_rewriter = searcher_with_rewriter
    mock_rewriter.rewrite.return_value = RewrittenQuery(
        terms=["find_oldest", "animal", "shelter"],
        focus="implementation",
    )

    results = s.search("how do you find the oldest animal?", rewrite=True)
    mock_rewriter.rewrite.assert_called_once()
    assert len(results) > 0


def test_search_rewrite_fallback_on_failure(searcher_with_rewriter):
    """If rewriter returns None, fall back to normal search."""
    s, mock_rewriter = searcher_with_rewriter
    mock_rewriter.rewrite.return_value = None

    results = s.search("find_oldest", rewrite=True, text_only=True)
    # Should still return results via normal search path
    assert len(results) > 0


def test_search_zero_results_triggers_rewrite(searcher_with_rewriter):
    """When initial search returns nothing, try LLM rewrite as fallback."""
    s, mock_rewriter = searcher_with_rewriter
    mock_rewriter.rewrite.return_value = RewrittenQuery(
        terms=["find_oldest", "Animal"],
        focus="all",
    )

    # Query that would normally return zero results
    results = s.search("xyzzy_nonexistent_gibberish_query", text_only=True)
    # The rewriter should have been called as fallback
    mock_rewriter.rewrite.assert_called_once()


def test_search_no_rewriter_still_works(searcher):
    """Searcher without a rewriter should work exactly as before."""
    results = searcher.search("oldest animal", text_only=True)
    assert len(results) > 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_searcher.py::test_search_with_forced_rewrite -v`
Expected: FAIL — `Searcher.__init__` doesn't accept `rewriter` yet.

**Step 3: Modify Searcher to accept rewriter and wire up the rewrite flow**

In `src/codelibrarian/searcher.py`, modify the `Searcher` class:

1. Update `__init__` (line 17):

```python
def __init__(
    self,
    store: SQLiteStore,
    embedder: EmbeddingClient | None = None,
    rewriter: "QueryRewriter | None" = None,
):
    self.store = store
    self.embedder = embedder
    self.rewriter = rewriter
```

2. Add the import at the top of the file (after line 8):

```python
from codelibrarian.models import RewrittenQuery, SearchResult, SymbolRecord
```

3. Replace the `search()` method (lines 25-87) with:

```python
def search(
    self,
    query: str,
    limit: int = 10,
    semantic_only: bool = False,
    text_only: bool = False,
    rewrite: bool = False,
) -> list[SearchResult]:
    # --- Graph intent routing ---
    intent = _classify_intent(query)
    if intent is not None:
        intent_type, symbol_name = intent
        result = self._dispatch_graph(intent_type, symbol_name, limit)
        if result is not None:
            return result

    # --- Query rewrite decision ---
    rewritten: RewrittenQuery | None = None
    if self.rewriter:
        if rewrite or _should_rewrite(query):
            rewritten = self.rewriter.rewrite(query)

    # --- Run search (rewritten or original) ---
    if rewritten:
        results = self._hybrid_search(
            " ".join(rewritten.terms), limit, semantic_only, text_only
        )
        results = _apply_focus(results, rewritten.focus)
    else:
        results = self._hybrid_search(query, limit, semantic_only, text_only)

    # --- Zero-results fallback: try LLM rewrite ---
    if not results and self.rewriter and not rewritten:
        rewritten = self.rewriter.rewrite(query)
        if rewritten:
            results = self._hybrid_search(
                " ".join(rewritten.terms), limit, semantic_only, text_only
            )
            results = _apply_focus(results, rewritten.focus)

    return results[:limit]
```

4. Extract the existing hybrid search logic into `_hybrid_search()` — a private method on `Searcher`:

```python
def _hybrid_search(
    self,
    query: str,
    limit: int,
    semantic_only: bool,
    text_only: bool,
) -> list[SearchResult]:
    """Core hybrid search (FTS + vector). Extracted for reuse by rewrite path."""
    fts_hits: dict[int, float] = {}
    vec_hits: dict[int, float] = {}

    if not text_only and self.embedder:
        query_vec = self.embedder.embed_one(query)
        if query_vec:
            for sym_id, dist in self.store.vector_search(query_vec, limit=limit * 2):
                vec_hits[sym_id] = max(0.0, 1.0 - dist / 2.0)

    if not semantic_only:
        safe_query = _fts5_query(query)
        if safe_query:
            for sym_id, score in self.store.fts_search(safe_query, limit=limit * 2):
                fts_hits[sym_id] = min(score / _BM25_SCALE, 1.0)
        if not fts_hits:
            or_query = _fts5_query(query, use_or=True)
            if or_query and or_query != safe_query:
                for sym_id, score in self.store.fts_search(or_query, limit=limit * 2):
                    fts_hits[sym_id] = min(score / _BM25_SCALE, 1.0)

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
```

5. Add the `_apply_focus` function after `_is_test_file`:

```python
def _apply_focus(results: list[SearchResult], focus: str) -> list[SearchResult]:
    """Adjust scores based on focus signal and re-sort."""
    if focus == "all":
        return results

    adjusted = []
    for r in results:
        path = r.symbol.relative_path or r.symbol.file_path
        is_test = _is_test_file(path)
        score = r.score
        if focus == "implementation" and is_test:
            score *= 0.7
        elif focus == "tests" and not is_test:
            score *= 0.7
        adjusted.append(SearchResult(symbol=r.symbol, score=score, match_type=r.match_type))

    adjusted.sort(key=lambda r: r.score, reverse=True)
    return adjusted
```

**Step 4: Run the new tests**

Run: `pytest tests/test_searcher.py::test_search_with_forced_rewrite tests/test_searcher.py::test_search_rewrite_fallback_on_failure tests/test_searcher.py::test_search_zero_results_triggers_rewrite tests/test_searcher.py::test_search_no_rewriter_still_works -v`
Expected: All PASS.

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS — existing tests still work because `rewriter` defaults to `None`.

**Step 6: Commit**

```bash
git add src/codelibrarian/searcher.py tests/test_searcher.py
git commit -m "feat: wire query rewriting into Searcher.search() with focus adjustment"
```

---

### Task 6: Add `--rewrite` flag to CLI search command

**Files:**
- Modify: `src/codelibrarian/cli.py:146-197` (search command)

**Step 1: Add the flag and rewriter construction**

In `src/codelibrarian/cli.py`, modify the `search` command:

Add `--rewrite` option after `--text-only` (after line 151):

```python
@click.option("--rewrite", "-r", is_flag=True, help="Force LLM query rewriting")
```

Update the function signature (line 152):

```python
def search(query: str, limit: int, semantic_only: bool, text_only: bool, rewrite: bool, path: str | None):
```

Add rewriter construction after the embedder setup (after line 183), before `with SQLiteStore`:

```python
    rewriter = None
    if config.query_rewrite_enabled:
        from codelibrarian.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(
            api_url=config.query_rewrite_api_url,
            model=config.query_rewrite_model,
            timeout=config.query_rewrite_timeout,
        )
```

Update the Searcher construction (line 175 area):

```python
        searcher = Searcher(store, embedder, rewriter=rewriter)
```

Update the search call (line 176 area):

```python
        results = searcher.search(
            query,
            limit=limit,
            semantic_only=semantic_only,
            text_only=text_only,
            rewrite=rewrite,
        )
```

Add cleanup after the `with` block (after embedder close):

```python
    if rewriter:
        rewriter.close()
```

**Step 2: Run existing tests**

Run: `pytest tests/ -v`
Expected: All PASS.

**Step 3: Commit**

```bash
git add src/codelibrarian/cli.py
git commit -m "feat: add --rewrite flag to CLI search command"
```

---

### Task 7: Add `rewrite` parameter to MCP `search_code` tool

**Files:**
- Modify: `src/codelibrarian/mcp_server.py:20-34` (_make_server)
- Modify: `src/codelibrarian/mcp_server.py:42-72` (search_code tool definition)
- Modify: `src/codelibrarian/mcp_server.py:295-311` (_dispatch search_code handler)

**Step 1: Add rewriter to _make_server**

In `src/codelibrarian/mcp_server.py`, modify `_make_server` (after embedder setup, before `searcher = Searcher(...)`, around line 33):

```python
    rewriter = None
    if config.query_rewrite_enabled:
        from codelibrarian.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(
            api_url=config.query_rewrite_api_url,
            model=config.query_rewrite_model,
            timeout=config.query_rewrite_timeout,
        )

    searcher = Searcher(store, embedder, rewriter=rewriter)
```

Update the return to include rewriter for cleanup (line 292):

```python
    return server, store, embedder, rewriter
```

**Step 2: Add `rewrite` to the search_code tool inputSchema**

In the `search_code` Tool definition (around line 63), add after the `mode` property:

```python
                        "rewrite": {
                            "type": "boolean",
                            "default": False,
                            "description": "Force LLM-based query rewriting for better natural language understanding",
                        },
```

**Step 3: Pass rewrite to dispatch**

In `_dispatch` (around line 301), update the search_code handler:

```python
    if name == "search_code":
        query = args["query"]
        limit = int(args.get("limit", 10))
        mode = args.get("mode", "hybrid")
        rewrite = bool(args.get("rewrite", False))
        results = searcher.search(
            query,
            limit=limit,
            semantic_only=(mode == "semantic"),
            text_only=(mode == "fulltext"),
            rewrite=rewrite,
        )
        return [r.to_dict() for r in results]
```

**Step 4: Update `run_server` cleanup**

In `run_server` (around line 397), update the destructuring and finally block:

```python
    server, store, embedder, rewriter = _make_server(config)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        store.close()
        if embedder:
            embedder.close()
        if rewriter:
            rewriter.close()
```

**Step 5: Run existing tests**

Run: `pytest tests/ -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add src/codelibrarian/mcp_server.py
git commit -m "feat: add rewrite parameter to MCP search_code tool"
```

---

### Task 8: Manual end-to-end verification

**Step 1: Ensure qwen2.5:3b is available**

Run: `ollama list | grep qwen2.5:3b`
Expected: Model listed.

**Step 2: Reindex the project**

Run: `codelibrarian index --full`

**Step 3: Test the original failing query without rewrite**

Run: `codelibrarian search "how are edges inserted into the graph?"`
Expected: Same results as before (test files, resolve_graph_edges).

**Step 4: Test with forced rewrite**

Run: `codelibrarian search "how are edges inserted into the graph?" --rewrite`
Expected: Better results — should show `store_parse_result`, `insert_call`, `insert_import`, or similar implementation symbols. Test files should rank lower.

**Step 5: Test that auto-rewrite triggers for natural language**

Run: `codelibrarian search "how does the indexer discover files"`
Expected: The `_should_rewrite()` heuristic should trigger automatically. Results should include `index_root`, `_discover_files`, or similar.

**Step 6: Test that code-like queries skip the LLM**

Run: `codelibrarian search "store.insert_call"`
Expected: Fast results (no LLM latency), matching the dotted symbol directly.

**Step 7: Test that test-focused queries work**

Run: `codelibrarian search "how are graph edges tested" --rewrite`
Expected: The LLM should return `focus: "tests"`, and test files should rank higher.

**Step 8: Test zero-results fallback**

Run: `codelibrarian search "xyzzy_nonexistent" --text-only`
Expected: First search finds nothing, fallback triggers LLM rewrite (which may also find nothing, but shouldn't crash).

**Step 9: Commit if adjustments were needed**

```bash
git add -u
git commit -m "fix: adjust query rewriting based on e2e testing"
```
