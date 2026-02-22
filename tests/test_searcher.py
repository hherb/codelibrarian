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
