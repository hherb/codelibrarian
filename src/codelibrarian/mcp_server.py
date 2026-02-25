"""MCP server: exposes codelibrarian tools to LLM clients via stdio transport."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from codelibrarian.config import Config
from codelibrarian.embeddings import EmbeddingClient
from codelibrarian.searcher import Searcher
from codelibrarian.storage.store import SQLiteStore

import json


def _make_server(config: Config) -> tuple[Server, SQLiteStore, EmbeddingClient | None, "QueryRewriter | None"]:
    store = SQLiteStore(config.db_path, config.embedding_dimensions)
    store.connect()

    embedder = None
    if config.embeddings_enabled:
        embedder = EmbeddingClient(
            api_url=config.embedding_api_url,
            model=config.embedding_model,
            dimensions=config.embedding_dimensions,
            batch_size=config.embedding_batch_size,
            max_chars=config.embedding_max_chars,
        )

    rewriter = None
    if config.query_rewrite_enabled:
        from codelibrarian.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(
            api_url=config.query_rewrite_api_url,
            model=config.query_rewrite_model,
            timeout=config.query_rewrite_timeout,
        )

    searcher = Searcher(store, embedder, rewriter=rewriter)
    server = Server("codelibrarian")

    # ------------------------------------------------------------------ #
    # Tool: search_code
    # ------------------------------------------------------------------ #

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="search_code",
                description=(
                    "Hybrid semantic + full-text search across all indexed code symbols. "
                    "Returns functions, methods, and classes matching the query with "
                    "file path and line number."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language or keyword search query",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "Maximum number of results to return",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["hybrid", "semantic", "fulltext"],
                            "default": "hybrid",
                            "description": "Search mode",
                        },
                        "rewrite": {
                            "type": "boolean",
                            "default": False,
                            "description": "Force LLM-based query rewriting for better natural language understanding",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="lookup_symbol",
                description=(
                    "Look up a code symbol by exact name or qualified name. "
                    "Returns full signature, docstring, parameters, return type, "
                    "file path and line number."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Symbol name (e.g. 'parse_config' or 'MyClass.my_method')",
                        }
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="get_callers",
                description="Find all functions/methods that call the specified symbol.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": "Qualified name of the symbol",
                        },
                        "depth": {
                            "type": "integer",
                            "default": 1,
                            "description": "How many call-graph hops to traverse",
                        },
                    },
                    "required": ["qualified_name"],
                },
            ),
            Tool(
                name="get_callees",
                description="Find all functions/methods called by the specified symbol.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": "Qualified name of the symbol",
                        },
                        "depth": {
                            "type": "integer",
                            "default": 1,
                            "description": "How many call-graph hops to traverse",
                        },
                    },
                    "required": ["qualified_name"],
                },
            ),
            Tool(
                name="get_file_imports",
                description=(
                    "Show what modules a file imports and what other files import it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file (relative or absolute)",
                        }
                    },
                    "required": ["file_path"],
                },
            ),
            Tool(
                name="list_symbols",
                description=(
                    "List symbols filtered by kind, name pattern, or file. "
                    "Useful for structural queries like 'all classes in module x'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["function", "method", "class", "module"],
                            "description": "Filter by symbol kind",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "SQL LIKE pattern for name filtering (e.g. 'get_%')",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Filter to symbols in this file",
                        },
                    },
                },
            ),
            Tool(
                name="get_class_hierarchy",
                description=(
                    "Get the inheritance hierarchy for a class: its parent classes "
                    "and all known subclasses."
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
                name="count_callers",
                description=(
                    "Return the number of direct callers of a symbol. "
                    "Efficient alternative to get_callers when only the count is needed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": "Qualified name of the symbol",
                        }
                    },
                    "required": ["qualified_name"],
                },
            ),
            Tool(
                name="count_callees",
                description=(
                    "Return the number of direct callees of a symbol. "
                    "Efficient alternative to get_callees when only the count is needed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": "Qualified name of the symbol",
                        }
                    },
                    "required": ["qualified_name"],
                },
            ),
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
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            result = _dispatch(name, arguments, searcher, config)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as exc:
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    return server, store, embedder, rewriter


def _dispatch(
    name: str,
    args: dict[str, Any],
    searcher: Searcher,
    config: Config,
) -> Any:
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

    elif name == "lookup_symbol":
        symbols = searcher.lookup_symbol(args["name"])
        return [s.to_dict() for s in symbols]

    elif name == "get_callers":
        depth = int(args.get("depth", 1))
        symbols = searcher.get_callers(args["qualified_name"], depth=depth)
        return [s.to_dict() for s in symbols]

    elif name == "get_callees":
        depth = int(args.get("depth", 1))
        symbols = searcher.get_callees(args["qualified_name"], depth=depth)
        return [s.to_dict() for s in symbols]

    elif name == "get_file_imports":
        file_path = args["file_path"]
        # Resolve relative paths against the index root
        p = Path(file_path)
        if not p.is_absolute():
            p = config.index_root / p
        return searcher.get_file_imports(str(p))

    elif name == "list_symbols":
        return [
            s.to_dict()
            for s in searcher.list_symbols(
                kind=args.get("kind"),
                pattern=args.get("pattern"),
                file_path=args.get("file_path"),
            )
        ]

    elif name == "get_class_hierarchy":
        return searcher.get_class_hierarchy(args["class_name"])

    elif name == "count_callers":
        qn = args["qualified_name"]
        row = searcher.store.conn.execute(
            """
            SELECT COUNT(DISTINCT c.caller_id) AS cnt
            FROM calls c
            JOIN symbols s ON c.callee_id = s.id
            WHERE s.qualified_name = ? OR s.name = ?
            """,
            (qn, qn),
        ).fetchone()
        return {"count": row["cnt"] if row else 0, "qualified_name": qn}

    elif name == "count_callees":
        qn = args["qualified_name"]
        row = searcher.store.conn.execute(
            """
            SELECT COUNT(DISTINCT c.callee_id) AS cnt
            FROM calls c
            JOIN symbols s ON c.caller_id = s.id
            WHERE s.qualified_name = ? OR s.name = ?
            """,
            (qn, qn),
        ).fetchone()
        return {"count": row["cnt"] if row else 0, "qualified_name": qn}

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

    else:
        raise ValueError(f"Unknown tool: {name}")


async def run_server(project_root: Path | None = None) -> None:
    config = (
        Config.load(project_root)
        if project_root
        else Config.load_from_cwd()
    )

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
