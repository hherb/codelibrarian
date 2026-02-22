# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Codelibrarian is a self-maintaining code index for LLM and human queries. It indexes code symbols (functions, methods, classes, modules) across multiple languages, builds call graphs and inheritance hierarchies, and exposes hybrid search (semantic embeddings + BM25 full-text) via an MCP server and CLI. Uses SQLite with sqlite-vec for vector search and FTS5 for full-text search.

## Commands

```bash
# Install dependencies (uv is the package manager)
uv sync

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_parsers.py::test_python_parser_finds_classes -v

# CLI usage (after install)
codelibrarian init          # Create .codelibrarian/ dir with config and DB
codelibrarian index         # Index the project
codelibrarian index --full  # Reindex everything (ignore hash cache)
codelibrarian search "query"
codelibrarian serve         # Start MCP server on stdio
```

No linter or formatter is configured in this project.

## Architecture

The codebase follows a pipeline: **Discovery -> Parsing -> Storage -> Search -> MCP/CLI**.

### Data Flow

1. **Indexer** (`indexer.py`) discovers files, delegates to parsers, stores results, then runs an embedding pass
2. **Parsers** produce `ParseResult` containing `Symbol` objects and `GraphEdges` (imports, calls, inheritance)
3. **SQLiteStore** (`storage/store.py`) persists everything: files, symbols, FTS5 index, vec0 embeddings, and graph edges (imports/calls/inherits tables)
4. **Searcher** (`searcher.py`) merges vector similarity + BM25 scores into ranked hybrid results
5. **MCP Server** (`mcp_server.py`) and **CLI** (`cli.py`) are thin wrappers over Searcher

### Key Design Decisions

- **Two parser strategies**: Python uses `ast` module directly (richer extraction of params, decorators, calls). All other languages use tree-sitter.
- **Graph edges are resolved post-index**: Edges are first stored with string names, then `resolve_graph_edges()` links them to actual symbol IDs via name matching.
- **Embeddings are optional**: Search degrades gracefully to FTS-only when the embedding API is unavailable. The default embedding endpoint is Ollama at `localhost:11434`.
- **Incremental indexing**: Files are skipped if their SHA256 hash hasn't changed. `--full` flag bypasses this.
- **Recursive CTEs** in SQLite power `get_callers`/`get_callees`/`get_class_hierarchy` with depth limits.

### Module Roles

| Module | Role |
|--------|------|
| `config.py` | Loads `.codelibrarian/config.toml`, merges with defaults, handles path exclusion and language detection |
| `models.py` | Dataclasses: `Symbol`, `ParseResult`, `GraphEdges`, `SymbolRecord`, `SearchResult` |
| `parsers/python_parser.py` | AST visitor extracting symbols, params, calls, imports, inheritance |
| `parsers/treesitter_parser.py` | Tree-sitter parser for TS/JS/Rust/Java/C++ |
| `parsers/__init__.py` | Factory: `get_parser(language)` returns the right parser singleton |
| `storage/store.py` | All SQLite access: schema, CRUD, FTS5, vec0, recursive CTE queries |
| `indexer.py` | Orchestrates discovery, parsing, storage, embedding |
| `searcher.py` | Hybrid search merging semantic + fulltext scores |
| `embeddings.py` | OpenAI-compatible embedding API client (httpx) |
| `mcp_server.py` | MCP stdio server exposing 7 tools |
| `cli.py` | Click CLI: init, index, search, lookup, status, serve, hooks |

### Database Schema

The SQLite DB (`.codelibrarian/index.db`) has these core tables:
- `files` — indexed files with content hash for incremental detection
- `symbols` — code symbols with parent_id for nesting (class -> method)
- `symbols_fts` — FTS5 virtual table with auto-sync triggers
- `symbol_embeddings` — vec0 virtual table (float[768] vectors)
- `imports`, `calls`, `inherits` — graph edge tables with composite PKs

## Conventions

- Python 3.11+ required
- All models are `@dataclass` with `to_dict()`/`from_dict()` serialization
- Store and EmbeddingClient are context managers (`with` statement)
- Parsers return empty `ParseResult` on syntax errors (never raise)
- Test fixtures live in `tests/fixtures/` with sample Python and TypeScript files
- `asyncio_mode = "auto"` in pytest config — async tests don't need `@pytest.mark.asyncio`
