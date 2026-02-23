"""Tests for the SQLiteStore: CRUD, FTS5, and graph operations."""

import tempfile
from pathlib import Path

import pytest

from codelibrarian.models import GraphEdges, Parameter, ParseResult, Symbol
from codelibrarian.storage.store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    db = SQLiteStore(tmp_path / "test.db", embedding_dimensions=4)
    with db:
        db.init_schema()
        yield db


def _make_symbol(name, qualified_name, kind, file_path="/fake/file.py", line=1):
    return Symbol(
        name=name,
        qualified_name=qualified_name,
        kind=kind,
        file_path=file_path,
        line_start=line,
        line_end=line + 5,
        signature=f"def {name}()",
        docstring=f"Docstring for {name}",
        parameters=[Parameter("x", "int")],
        return_type="None",
    )


# --------------------------------------------------------------------------- #
# File operations
# --------------------------------------------------------------------------- #


def test_upsert_and_get_file(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "abc123")
    assert isinstance(fid, int)
    assert store.get_file_hash("/a/b.py") == "abc123"


def test_upsert_file_is_idempotent(store):
    id1 = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "hash1")
    id2 = store.upsert_file("/a/b.py", "b.py", "python", 2.0, "hash2")
    assert id1 == id2
    assert store.get_file_hash("/a/b.py") == "hash2"


# --------------------------------------------------------------------------- #
# Symbol operations
# --------------------------------------------------------------------------- #


def test_insert_and_lookup_symbol(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("foo", "module.foo", "function")
    sym_id = store.insert_symbol(sym, fid, None)
    assert isinstance(sym_id, int)

    result = store.lookup_symbol("foo")
    assert len(result) == 1
    assert result[0].name == "foo"
    assert result[0].qualified_name == "module.foo"


def test_symbol_parameters_roundtrip(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("bar", "module.bar", "function")
    sym.parameters = [Parameter("a", "int", "0"), Parameter("b", "str", None)]
    store.insert_symbol(sym, fid, None)

    result = store.lookup_symbol("bar")[0]
    assert len(result.parameters) == 2
    assert result.parameters[0].name == "a"
    assert result.parameters[0].type == "int"
    assert result.parameters[0].default == "0"


def test_delete_file_symbols_cascade(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("baz", "module.baz", "function")
    store.insert_symbol(sym, fid, None)
    store.conn.commit()

    assert len(store.lookup_symbol("baz")) == 1
    store.delete_file_symbols(fid)
    store.conn.commit()
    assert len(store.lookup_symbol("baz")) == 0


# --------------------------------------------------------------------------- #
# FTS5
# --------------------------------------------------------------------------- #


def test_fts_search_finds_by_name(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("authenticate_user", "auth.authenticate_user", "function")
    sym.docstring = "Validates user credentials and returns a session token"
    store.insert_symbol(sym, fid, None)
    store.conn.commit()

    results = store.fts_search("authenticate")
    assert any(r[0] for r in results)


def test_fts_search_finds_by_docstring(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("connect_db", "db.connect_db", "function")
    sym.docstring = "Establishes a database migration connection"
    store.insert_symbol(sym, fid, None)
    store.conn.commit()

    results = store.fts_search("migration")
    ids = [r[0] for r in results]
    assert len(ids) > 0


def test_fts_trigger_on_delete(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("special_func", "m.special_func", "function")
    sym.docstring = "unique_token_xyz"
    sym_id = store.insert_symbol(sym, fid, None)
    store.conn.commit()

    assert len(store.fts_search("unique_token_xyz")) > 0

    store.delete_file_symbols(fid)
    store.conn.commit()
    assert len(store.fts_search("unique_token_xyz")) == 0


# --------------------------------------------------------------------------- #
# Vector embeddings
# --------------------------------------------------------------------------- #


def test_upsert_and_search_embedding(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    sym = _make_symbol("vec_func", "m.vec_func", "function")
    sym_id = store.insert_symbol(sym, fid, None)
    store.conn.commit()

    embedding = [0.1, 0.2, 0.3, 0.4]
    store.upsert_embedding(sym_id, embedding)
    store.conn.commit()

    results = store.vector_search([0.1, 0.2, 0.3, 0.4], limit=5)
    assert len(results) == 1
    assert results[0][0] == sym_id


# --------------------------------------------------------------------------- #
# Graph: calls
# --------------------------------------------------------------------------- #


def test_call_graph(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    caller = _make_symbol("caller_fn", "m.caller_fn", "function")
    callee = _make_symbol("callee_fn", "m.callee_fn", "function")
    caller_id = store.insert_symbol(caller, fid, None)
    callee_id = store.insert_symbol(callee, fid, None)
    store.conn.commit()

    store.insert_call(caller_id, "m.callee_fn")
    store.resolve_graph_edges()
    store.conn.commit()

    callees = store.get_callees("m.caller_fn")
    assert any(s.name == "callee_fn" for s in callees)

    callers = store.get_callers("m.callee_fn")
    assert any(s.name == "caller_fn" for s in callers)


def test_call_graph_dotted_callee(store):
    """Dotted callee names like 'obj.method' should resolve via suffix matching."""
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    caller = _make_symbol("my_func", "m.my_func", "function")
    method = _make_symbol("do_work", "m.SomeClass.do_work", "method")
    caller_id = store.insert_symbol(caller, fid, None)
    store.insert_symbol(method, fid, None)
    store.conn.commit()

    # Parser extracts "obj.do_work" — the variable prefix won't match any
    # qualified_name or name directly, but the suffix "do_work" should.
    store.insert_call(caller_id, "obj.do_work")
    store.resolve_graph_edges()
    store.conn.commit()

    callees = store.get_callees("m.my_func")
    assert any(s.name == "do_work" for s in callees)


def test_call_graph_deeply_dotted_callee(store):
    """Deeply dotted names like 'self.store.method' should also resolve."""
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    caller = _make_symbol("handler", "m.handler", "function")
    method = _make_symbol("execute", "m.DB.execute", "method")
    caller_id = store.insert_symbol(caller, fid, None)
    store.insert_symbol(method, fid, None)
    store.conn.commit()

    store.insert_call(caller_id, "self.db.execute")
    store.resolve_graph_edges()
    store.conn.commit()

    callees = store.get_callees("m.handler")
    assert any(s.name == "execute" for s in callees)


# --------------------------------------------------------------------------- #
# Graph: inheritance
# --------------------------------------------------------------------------- #


def test_inheritance_hierarchy(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    parent = _make_symbol("Base", "m.Base", "class")
    child = _make_symbol("Child", "m.Child", "class")
    parent_id = store.insert_symbol(parent, fid, None)
    child_id = store.insert_symbol(child, fid, None)
    store.conn.commit()

    store.insert_inherit(child_id, "m.Base")
    store.resolve_graph_edges()
    store.conn.commit()

    hierarchy = store.get_class_hierarchy("Base")
    assert hierarchy["class"] is not None
    child_names = [c["name"] for c in hierarchy["children"]]
    assert "Child" in child_names


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #


def test_stats(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    store.insert_symbol(_make_symbol("f1", "m.f1", "function"), fid, None)
    store.insert_symbol(_make_symbol("C1", "m.C1", "class"), fid, None)
    store.conn.commit()

    s = store.stats()
    assert s["files"] == 1
    assert s["symbols"]["function"] == 1
    assert s["symbols"]["class"] == 1
