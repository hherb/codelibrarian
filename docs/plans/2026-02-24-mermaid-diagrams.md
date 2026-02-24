# Mermaid Diagram Generation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Mermaid diagram generation (class hierarchy, call graph, module imports) to codelibrarian as CLI commands and MCP tools.

**Architecture:** A new `diagrams.py` module converts existing graph data from SQLiteStore into Mermaid syntax strings. Two new SQL edge-query methods feed directed-edge data to the renderers. CLI and MCP layers are thin wrappers that call `diagrams.py` and return the Mermaid text.

**Tech Stack:** Pure Python, no new dependencies. Output is Mermaid markdown text.

---

### Task 1: Add edge-returning query methods to SQLiteStore

**Files:**
- Modify: `src/codelibrarian/storage/store.py`
- Test: `tests/test_store.py`

**Step 1: Write failing tests for `get_call_edges` and `get_all_import_edges`**

Add to `tests/test_store.py`:

```python
def test_get_call_edges(store):
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    a = _make_symbol("a_fn", "m.a_fn", "function")
    b = _make_symbol("b_fn", "m.b_fn", "function")
    c = _make_symbol("c_fn", "m.c_fn", "function")
    a_id = store.insert_symbol(a, fid, None)
    b_id = store.insert_symbol(b, fid, None)
    c_id = store.insert_symbol(c, fid, None)
    store.conn.commit()

    store.insert_call(a_id, "m.b_fn")
    store.insert_call(b_id, "m.c_fn")
    store.resolve_graph_edges()
    store.conn.commit()

    # depth=1: only direct calls from a_fn
    edges = store.get_call_edges("m.a_fn", depth=1, direction="callees")
    assert ("m.a_fn", "m.b_fn") in edges

    # depth=2: transitive
    edges = store.get_call_edges("m.a_fn", depth=2, direction="callees")
    assert ("m.a_fn", "m.b_fn") in edges
    assert ("m.b_fn", "m.c_fn") in edges

    # callers direction
    edges = store.get_call_edges("m.c_fn", depth=2, direction="callers")
    assert ("m.a_fn", "m.b_fn") in edges
    assert ("m.b_fn", "m.c_fn") in edges


def test_get_all_import_edges(store):
    fid1 = store.upsert_file("/a/mod_a.py", "mod_a.py", "python", 1.0, "x")
    fid2 = store.upsert_file("/a/mod_b.py", "mod_b.py", "python", 1.0, "y")

    store.insert_import(fid1, "mod_b")
    # Resolve: simulate to_file_id being set
    store.conn.execute(
        "UPDATE imports SET to_file_id = ? WHERE from_file_id = ? AND to_module = ?",
        (fid2, fid1, "mod_b"),
    )
    store.conn.commit()

    edges = store.get_all_import_edges()
    assert ("mod_a.py", "mod_b.py") in edges
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py::test_get_call_edges tests/test_store.py::test_get_all_import_edges -v`
Expected: FAIL — `AttributeError: 'SQLiteStore' object has no attribute 'get_call_edges'`

**Step 3: Implement `get_call_edges` and `get_all_import_edges` in store.py**

Add to `src/codelibrarian/storage/store.py` after the existing `get_callees` method:

```python
def get_call_edges(
    self,
    qualified_name: str,
    depth: int = 1,
    direction: str = "callees",
) -> list[tuple[str, str]]:
    """Return directed (caller_qname, callee_qname) edge pairs.

    *direction* is ``"callees"`` (forward from the root) or ``"callers"``
    (backward to the root).  Recursive CTE traverses up to *depth* hops.
    """
    if direction == "callees":
        rows = self.conn.execute(
            """
            WITH RECURSIVE edge_tree(caller_id, callee_id, depth) AS (
                SELECT c.caller_id, c.callee_id, 1
                FROM calls c
                JOIN symbols s ON c.caller_id = s.id
                WHERE (s.qualified_name = ? OR s.name = ?)
                  AND c.callee_id IS NOT NULL
                UNION
                SELECT c2.caller_id, c2.callee_id, et.depth + 1
                FROM calls c2
                JOIN edge_tree et ON c2.caller_id = et.callee_id
                WHERE et.depth < ? AND c2.callee_id IS NOT NULL
            )
            SELECT DISTINCT
                s1.qualified_name AS caller_qname,
                s2.qualified_name AS callee_qname
            FROM edge_tree et
            JOIN symbols s1 ON et.caller_id = s1.id
            JOIN symbols s2 ON et.callee_id = s2.id
            """,
            (qualified_name, qualified_name, depth),
        ).fetchall()
    else:
        rows = self.conn.execute(
            """
            WITH RECURSIVE edge_tree(caller_id, callee_id, depth) AS (
                SELECT c.caller_id, c.callee_id, 1
                FROM calls c
                JOIN symbols s ON c.callee_id = s.id
                WHERE (s.qualified_name = ? OR s.name = ?)
                  AND c.caller_id IS NOT NULL
                UNION
                SELECT c2.caller_id, c2.callee_id, et.depth + 1
                FROM calls c2
                JOIN edge_tree et ON c2.callee_id = et.caller_id
                WHERE et.depth < ? AND c2.caller_id IS NOT NULL
            )
            SELECT DISTINCT
                s1.qualified_name AS caller_qname,
                s2.qualified_name AS callee_qname
            FROM edge_tree et
            JOIN symbols s1 ON et.caller_id = s1.id
            JOIN symbols s2 ON et.callee_id = s2.id
            """,
            (qualified_name, qualified_name, depth),
        ).fetchall()
    return [(r["caller_qname"], r["callee_qname"]) for r in rows]


def get_all_import_edges(self) -> list[tuple[str, str]]:
    """Return all resolved file-to-file import edges as (from_path, to_path)."""
    rows = self.conn.execute(
        """
        SELECT f1.relative_path AS from_path, f2.relative_path AS to_path
        FROM imports i
        JOIN files f1 ON i.from_file_id = f1.id
        JOIN files f2 ON i.to_file_id = f2.id
        WHERE i.to_file_id IS NOT NULL
        """
    ).fetchall()
    return [(r["from_path"], r["to_path"]) for r in rows]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/codelibrarian/storage/store.py tests/test_store.py
git commit -m "feat: add get_call_edges and get_all_import_edges to store"
```

---

### Task 2: Create `diagrams.py` with Mermaid renderers

**Files:**
- Create: `src/codelibrarian/diagrams.py`
- Test: `tests/test_diagrams.py`

**Step 1: Write failing tests**

Create `tests/test_diagrams.py`:

```python
"""Tests for Mermaid diagram generation."""

import pytest

from codelibrarian.models import Parameter, Symbol
from codelibrarian.storage.store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    db = SQLiteStore(tmp_path / "test.db", embedding_dimensions=4)
    with db:
        db.init_schema()
        yield db


def _sym(name, qname, kind, file_path="/a/b.py", line=1, params=None, parent_qname=None):
    return Symbol(
        name=name,
        qualified_name=qname,
        kind=kind,
        file_path=file_path,
        line_start=line,
        line_end=line + 5,
        signature=f"def {name}()" if kind != "class" else f"class {name}",
        parameters=params or [],
        parent_qualified_name=parent_qname,
    )


def _setup_hierarchy(store):
    """Create Animal -> Dog, Animal -> Cat hierarchy with methods."""
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")

    animal_id = store.insert_symbol(_sym("Animal", "m.Animal", "class"), fid, None)
    store.insert_symbol(
        _sym("speak", "m.Animal.speak", "method", parent_qname="m.Animal"),
        fid, animal_id,
    )

    dog_id = store.insert_symbol(_sym("Dog", "m.Dog", "class"), fid, None)
    store.insert_symbol(
        _sym("fetch", "m.Dog.fetch", "method", parent_qname="m.Dog"),
        fid, dog_id,
    )

    cat_id = store.insert_symbol(_sym("Cat", "m.Cat", "class"), fid, None)

    store.insert_inherit(dog_id, "m.Animal")
    store.insert_inherit(cat_id, "m.Animal")
    store.resolve_graph_edges()
    store.conn.commit()
    return fid


def _setup_call_chain(store):
    """Create a -> b -> c call chain."""
    fid = store.upsert_file("/a/b.py", "b.py", "python", 1.0, "x")
    a_id = store.insert_symbol(_sym("a_fn", "m.a_fn", "function"), fid, None)
    b_id = store.insert_symbol(_sym("b_fn", "m.b_fn", "function"), fid, None)
    c_id = store.insert_symbol(_sym("c_fn", "m.c_fn", "function"), fid, None)
    store.conn.commit()

    store.insert_call(a_id, "m.b_fn")
    store.insert_call(b_id, "m.c_fn")
    store.resolve_graph_edges()
    store.conn.commit()
    return fid


class TestClassDiagram:
    def test_contains_mermaid_header(self, store):
        _setup_hierarchy(store)
        from codelibrarian.diagrams import mermaid_class_diagram
        result = mermaid_class_diagram(store, "Animal")
        assert result.startswith("classDiagram")

    def test_shows_inheritance(self, store):
        _setup_hierarchy(store)
        from codelibrarian.diagrams import mermaid_class_diagram
        result = mermaid_class_diagram(store, "Animal")
        assert "Animal <|-- Dog" in result
        assert "Animal <|-- Cat" in result

    def test_shows_methods(self, store):
        _setup_hierarchy(store)
        from codelibrarian.diagrams import mermaid_class_diagram
        result = mermaid_class_diagram(store, "Animal")
        assert "speak()" in result

    def test_unknown_class_returns_empty(self, store):
        from codelibrarian.diagrams import mermaid_class_diagram
        result = mermaid_class_diagram(store, "NoSuchClass")
        assert result == ""


class TestCallGraph:
    def test_contains_mermaid_header(self, store):
        _setup_call_chain(store)
        from codelibrarian.diagrams import mermaid_call_graph
        result = mermaid_call_graph(store, "m.a_fn", depth=2, direction="callees")
        assert result.startswith("flowchart LR")

    def test_shows_edges(self, store):
        _setup_call_chain(store)
        from codelibrarian.diagrams import mermaid_call_graph
        result = mermaid_call_graph(store, "m.a_fn", depth=2, direction="callees")
        assert "a_fn" in result
        assert "b_fn" in result
        assert "c_fn" in result
        assert "-->" in result

    def test_depth_limits_edges(self, store):
        _setup_call_chain(store)
        from codelibrarian.diagrams import mermaid_call_graph
        result = mermaid_call_graph(store, "m.a_fn", depth=1, direction="callees")
        assert "a_fn" in result
        assert "b_fn" in result
        # c_fn should NOT appear at depth=1
        assert "c_fn" not in result

    def test_unknown_symbol_returns_empty(self, store):
        from codelibrarian.diagrams import mermaid_call_graph
        result = mermaid_call_graph(store, "no.such.fn", depth=1, direction="callees")
        assert result == ""


class TestImportGraph:
    def test_contains_mermaid_header(self, store):
        fid1 = store.upsert_file("/a/mod_a.py", "src/mod_a.py", "python", 1.0, "x")
        fid2 = store.upsert_file("/a/mod_b.py", "src/mod_b.py", "python", 1.0, "y")
        store.insert_import(fid1, "mod_b")
        store.conn.execute(
            "UPDATE imports SET to_file_id = ? WHERE from_file_id = ?", (fid2, fid1)
        )
        store.conn.commit()

        from codelibrarian.diagrams import mermaid_import_graph
        result = mermaid_import_graph(store)
        assert result.startswith("flowchart LR")

    def test_shows_file_edges(self, store):
        fid1 = store.upsert_file("/a/mod_a.py", "src/mod_a.py", "python", 1.0, "x")
        fid2 = store.upsert_file("/a/mod_b.py", "src/mod_b.py", "python", 1.0, "y")
        store.insert_import(fid1, "mod_b")
        store.conn.execute(
            "UPDATE imports SET to_file_id = ? WHERE from_file_id = ?", (fid2, fid1)
        )
        store.conn.commit()

        from codelibrarian.diagrams import mermaid_import_graph
        result = mermaid_import_graph(store)
        assert "mod_a" in result
        assert "mod_b" in result
        assert "-->" in result

    def test_empty_project_returns_empty(self, store):
        from codelibrarian.diagrams import mermaid_import_graph
        result = mermaid_import_graph(store)
        assert result == ""
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_diagrams.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codelibrarian.diagrams'`

**Step 3: Implement `diagrams.py`**

Create `src/codelibrarian/diagrams.py` with these functions:

- `mermaid_class_diagram(store, class_name) -> str` — Queries `get_class_hierarchy` for parents/children, `list_symbols(kind='method', ...)` for methods on each class. Outputs `classDiagram` with inheritance arrows and method listings.
- `mermaid_call_graph(store, qualified_name, depth, direction) -> str` — Queries `get_call_edges`. Outputs `flowchart LR` with directed edges. Highlights the root node with bold styling.
- `mermaid_import_graph(store, file_path=None) -> str` — Queries `get_all_import_edges` (optionally filtered to edges involving `file_path`). Groups files by top-level directory into Mermaid subgraphs. Outputs `flowchart LR`.

Implementation details:
- Use `_sanitize_id(name)` helper to make valid Mermaid node IDs (replace dots/slashes with underscores).
- Use `_short_name(qualified_name)` helper to get display labels (last component of qualified name).
- Class diagram: list methods inside class boxes using `class ClassName { +method_name() }` syntax.
- Call graph: style root node differently: `style root_id fill:#f96,stroke:#333`
- Import graph: derive directory grouping from `os.path.dirname(relative_path)` for subgraph labels.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_diagrams.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/codelibrarian/diagrams.py tests/test_diagrams.py
git commit -m "feat: add Mermaid diagram generation module"
```

---

### Task 3: Add CLI `diagram` subcommands

**Files:**
- Modify: `src/codelibrarian/cli.py`

**Step 1: Add the `diagram` group and three subcommands**

Add a new Click group `diagram` to `cli.py` with subcommands:

```python
@main.group()
def diagram():
    """Generate Mermaid diagrams from the code index."""


@diagram.command("class")
@click.argument("name")
@click.option("--path", default=None, help="Project root")
def diagram_class(name: str, path: str | None):
    """Generate a class hierarchy diagram in Mermaid syntax."""
    root = Path(path).resolve() if path else None
    config = Config.load(root) if root else Config.load_from_cwd()

    if not config.db_path.exists():
        click.echo("No index found. Run 'codelibrarian init && codelibrarian index' first.")
        sys.exit(1)

    from codelibrarian.diagrams import mermaid_class_diagram
    from codelibrarian.storage.store import SQLiteStore

    with SQLiteStore(config.db_path, config.embedding_dimensions) as store:
        result = mermaid_class_diagram(store, name)

    if not result:
        click.echo(f"Class '{name}' not found in index.")
        sys.exit(1)
    click.echo(result)


@diagram.command("calls")
@click.argument("name")
@click.option("--depth", "-d", default=2, help="Call-graph hops to traverse")
@click.option(
    "--direction",
    type=click.Choice(["callees", "callers"]),
    default="callees",
    help="Traverse callees (forward) or callers (backward)",
)
@click.option("--path", default=None, help="Project root")
def diagram_calls(name: str, depth: int, direction: str, path: str | None):
    """Generate a call graph diagram in Mermaid syntax."""
    root = Path(path).resolve() if path else None
    config = Config.load(root) if root else Config.load_from_cwd()

    if not config.db_path.exists():
        click.echo("No index found. Run 'codelibrarian init && codelibrarian index' first.")
        sys.exit(1)

    from codelibrarian.diagrams import mermaid_call_graph
    from codelibrarian.storage.store import SQLiteStore

    with SQLiteStore(config.db_path, config.embedding_dimensions) as store:
        result = mermaid_call_graph(store, name, depth=depth, direction=direction)

    if not result:
        click.echo(f"Symbol '{name}' not found or has no call edges.")
        sys.exit(1)
    click.echo(result)


@diagram.command("imports")
@click.option("--file", "file_path", default=None, help="Scope to a single file")
@click.option("--path", default=None, help="Project root")
def diagram_imports(file_path: str | None, path: str | None):
    """Generate a module import graph diagram in Mermaid syntax."""
    root = Path(path).resolve() if path else None
    config = Config.load(root) if root else Config.load_from_cwd()

    if not config.db_path.exists():
        click.echo("No index found. Run 'codelibrarian init && codelibrarian index' first.")
        sys.exit(1)

    from codelibrarian.diagrams import mermaid_import_graph
    from codelibrarian.storage.store import SQLiteStore

    with SQLiteStore(config.db_path, config.embedding_dimensions) as store:
        result = mermaid_import_graph(store, file_path=file_path)

    if not result:
        click.echo("No import edges found in index.")
        sys.exit(1)
    click.echo(result)
```

**Step 2: Manual smoke test**

Run: `codelibrarian diagram --help`
Expected: Shows `class`, `calls`, `imports` subcommands

**Step 3: Commit**

```bash
git add src/codelibrarian/cli.py
git commit -m "feat: add diagram CLI subcommands"
```

---

### Task 4: Add MCP diagram tools

**Files:**
- Modify: `src/codelibrarian/mcp_server.py`

**Step 1: Add three new tools to `list_tools` and dispatch**

Add to the tools list in `list_tools()`:

```python
Tool(
    name="generate_class_diagram",
    description=(
        "Generate a Mermaid class hierarchy diagram for a given class, "
        "showing parents, children, and methods."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "class_name": {
                "type": "string",
                "description": "Class name or qualified class name",
            }
        },
        "required": ["class_name"],
    },
),
Tool(
    name="generate_call_graph",
    description=(
        "Generate a Mermaid call graph diagram rooted at a function/method, "
        "showing caller or callee relationships."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "qualified_name": {
                "type": "string",
                "description": "Qualified name of the root symbol",
            },
            "depth": {
                "type": "integer",
                "default": 2,
                "description": "Number of hops to traverse",
            },
            "direction": {
                "type": "string",
                "enum": ["callees", "callers"],
                "default": "callees",
                "description": "Traverse forward (callees) or backward (callers)",
            },
        },
        "required": ["qualified_name"],
    },
),
Tool(
    name="generate_import_graph",
    description=(
        "Generate a Mermaid diagram of file-to-file import dependencies, "
        "optionally scoped to a single file."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Optional file path to scope the graph to",
            }
        },
    },
),
```

Add dispatch cases in `_dispatch()`:

```python
elif name == "generate_class_diagram":
    from codelibrarian.diagrams import mermaid_class_diagram
    result = mermaid_class_diagram(searcher.store, args["class_name"])
    return {"mermaid": result} if result else {"error": "Class not found"}

elif name == "generate_call_graph":
    from codelibrarian.diagrams import mermaid_call_graph
    depth = int(args.get("depth", 2))
    direction = args.get("direction", "callees")
    result = mermaid_call_graph(
        searcher.store, args["qualified_name"], depth=depth, direction=direction
    )
    return {"mermaid": result} if result else {"error": "Symbol not found or no edges"}

elif name == "generate_import_graph":
    from codelibrarian.diagrams import mermaid_import_graph
    result = mermaid_import_graph(searcher.store, file_path=args.get("file_path"))
    return {"mermaid": result} if result else {"error": "No import edges found"}
```

**Step 2: Manual smoke test**

Run: `codelibrarian serve` and verify the new tools appear in tool listing via an MCP client.

**Step 3: Commit**

```bash
git add src/codelibrarian/mcp_server.py
git commit -m "feat: add diagram generation MCP tools"
```

---

### Task 5: Run full test suite and verify

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 2: End-to-end smoke test on the codelibrarian project itself**

```bash
codelibrarian index
codelibrarian diagram class SQLiteStore
codelibrarian diagram calls mermaid_class_diagram --depth 2
codelibrarian diagram imports
```

Expected: Each outputs valid Mermaid syntax.

**Step 3: Final commit if any fixups needed**

```bash
git add -A && git commit -m "fix: diagram generation fixups from smoke testing"
```
