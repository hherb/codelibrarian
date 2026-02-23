"""Tests for the Searcher: all query types."""

from pathlib import Path

import pytest

from codelibrarian.config import Config
from codelibrarian.indexer import Indexer
from codelibrarian.searcher import Searcher
from codelibrarian.storage.store import SQLiteStore

FIXTURES = Path(__file__).parent / "fixtures" / "python_sample"


@pytest.fixture
def searcher(tmp_path):
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

    yield Searcher(store, embedder=None)

    store.close()


def test_fulltext_search_finds_docstring(searcher):
    results = searcher.search("oldest animal", text_only=True)
    assert len(results) > 0
    names = [r.symbol.name for r in results]
    assert any("oldest" in n.lower() or "animal" in n.lower() for n in names)


def test_fulltext_search_finds_by_name(searcher):
    results = searcher.search("fetch", text_only=True)
    assert any(r.symbol.name == "fetch" for r in results)


def test_lookup_symbol_exact(searcher):
    results = searcher.lookup_symbol("Dog")
    assert len(results) > 0
    assert results[0].kind == "class"


def test_lookup_symbol_qualified(searcher):
    results = searcher.lookup_symbol("models.Dog.fetch")
    assert len(results) > 0
    assert results[0].name == "fetch"


def test_lookup_symbol_prefix(searcher):
    results = searcher.lookup_symbol("find_old")
    assert len(results) > 0
    assert any("find_oldest" in r.qualified_name for r in results)


def test_list_symbols_by_kind(searcher):
    classes = searcher.list_symbols(kind="class")
    kinds = {s.kind for s in classes}
    assert kinds == {"class"}
    names = {s.name for s in classes}
    assert "Animal" in names


def test_list_symbols_by_pattern(searcher):
    results = searcher.list_symbols(pattern="speak%")
    assert all("speak" in s.name for s in results)


def test_get_class_hierarchy(searcher):
    h = searcher.get_class_hierarchy("Animal")
    assert h["class"] is not None
    child_names = [c["name"] for c in h["children"]]
    assert "Dog" in child_names
    assert "Cat" in child_names


# --------------------------------------------------------------------------- #
# Intent classification tests
# --------------------------------------------------------------------------- #

from codelibrarian.searcher import _classify_intent


class TestClassifyIntent:
    """Tests for the regex-based intent classifier."""

    # -- callees patterns --
    def test_callees_what_does_x_call(self):
        assert _classify_intent("what does find_oldest call") == ("callees", "find_oldest")

    def test_callees_functions_called_by(self):
        assert _classify_intent("functions called by test_call_graph") == ("callees", "test_call_graph")

    def test_callees_callees_of(self):
        assert _classify_intent("callees of AnimalShelter.admit") == ("callees", "AnimalShelter.admit")

    def test_callees_which_functions_called_by(self):
        assert _classify_intent("which functions are called by find_oldest_resident") == ("callees", "find_oldest_resident")

    # -- callers patterns --
    def test_callers_who_calls(self):
        assert _classify_intent("who calls find_oldest") == ("callers", "find_oldest")

    def test_callers_what_calls(self):
        assert _classify_intent("what calls parse_config") == ("callers", "parse_config")

    def test_callers_callers_of(self):
        assert _classify_intent("callers of find_oldest") == ("callers", "find_oldest")

    def test_callers_where_is_x_used(self):
        assert _classify_intent("where is find_oldest used") == ("callers", "find_oldest")

    def test_callers_usages_of(self):
        assert _classify_intent("usages of find_oldest") == ("callers", "find_oldest")

    # -- hierarchy patterns --
    def test_hierarchy_subclasses_of(self):
        assert _classify_intent("subclasses of Animal") == ("hierarchy", "Animal")

    def test_hierarchy_inherits_from(self):
        assert _classify_intent("Dog inherits from what") == ("hierarchy", "Dog")

    def test_hierarchy_parent_class(self):
        assert _classify_intent("parent class of Dog") == ("hierarchy", "Dog")

    def test_hierarchy_children_of(self):
        assert _classify_intent("children of Animal") == ("hierarchy", "Animal")

    # -- no match (should fall through to hybrid search) --
    def test_no_match_conceptual_query(self):
        assert _classify_intent("how does authentication work") is None

    def test_no_match_keyword_search(self):
        assert _classify_intent("parse config toml") is None

    def test_no_match_empty(self):
        assert _classify_intent("") is None
