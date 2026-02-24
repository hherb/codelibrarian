# Codelibrarian

A self-maintaining code index for LLM and human queries via MCP and CLI.

Codelibrarian indexes your codebase — functions, methods, classes, modules — and lets you search it with natural language or keywords. It builds call graphs, tracks inheritance hierarchies, and maps import dependencies. Results are available through an MCP server (for LLM clients like Claude) or a command-line interface.

![Codelibrarian](assets/codelibrarian.png)

## How It Works

Codelibrarian parses your source files into a SQLite database with:

- **Symbol extraction** — functions, methods, classes, and modules with full signatures, docstrings, parameters, decorators, and return types
- **Hybrid search** — combines semantic vector search (via embeddings) with BM25 full-text search for ranked results
- **Call graph** — tracks which functions call which, traversable to arbitrary depth. Automatically filters out noise (builtins, stdlib, external dependencies) so only project-internal calls appear
- **Inheritance hierarchy** — maps parent/child class relationships
- **Import graph** — shows what each file imports and what imports it
- **Incremental indexing** — only re-indexes files that have changed (SHA256 hash comparison)
- **Mermaid diagrams** — generates class hierarchy, call graph, and module import diagrams in Mermaid syntax, renderable in GitHub, VS Code, and any markdown tool

## Diagrams

Codelibrarian can generate Mermaid diagrams directly from the index — no additional dependencies required. Output is Mermaid text that renders natively in GitHub markdown, VS Code preview, and most documentation tools.

```bash
# Class hierarchy with methods, parents, and children
codelibrarian diagram class Animal

# Call graph: what does index_root call, 2 hops deep
codelibrarian diagram calls index_root --depth 2

# Call graph: what calls process_payment (reverse direction)
codelibrarian diagram calls process_payment --direction callers

# Module import dependencies (whole project)
codelibrarian diagram imports

# Module import dependencies (scoped to one file)
codelibrarian diagram imports --file src/codelibrarian/searcher.py
```

The same diagrams are available via MCP tools (`generate_class_diagram`, `generate_call_graph`, `generate_import_graph`), so any LLM client can request them.

## Supported Languages

| Language   | Parser     | Extensions                     |
|------------|------------|--------------------------------|
| Python     | `ast`      | `.py`                          |
| TypeScript | tree-sitter| `.ts`, `.tsx`                  |
| JavaScript | tree-sitter| `.js`, `.jsx`, `.mjs`          |
| Rust       | tree-sitter| `.rs`                          |
| Java       | tree-sitter| `.java`                        |
| C/C++      | tree-sitter| `.c`, `.h`, `.cpp`, `.cc`, `.cxx`, `.hpp` |
| Swift      | tree-sitter| `.swift`                       |
| Kotlin     | tree-sitter| `.kt`, `.kts`                  |

Python gets deeper analysis (parameter defaults, decorators, call extraction) because it uses Python's own AST module. Swift and Kotlin have rich extractors (protocols/interfaces, extensions, data classes, suspend functions, doc comments). Other languages use tree-sitter grammars with basic class/method extraction.

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/hherb/codelibrarian.git
cd codelibrarian
uv tool install .
```

This installs `codelibrarian` as a standalone command on your PATH using uv's managed Python, which includes SQLite extension support required by sqlite-vec.

For development:

```bash
uv sync
uv run codelibrarian --help
```

> **Note:** `pip install .` also works but requires a Python build with SQLite extension loading enabled. macOS system Python and pyenv default builds lack this. If you hit `enable_load_extension` errors, use the `uv tool install` method above.

### Embedding Server (Optional)

For semantic search, codelibrarian needs an OpenAI-compatible embedding API. By default it expects [Ollama](https://ollama.com) running locally:

```bash
# Install and start Ollama, then pull the embedding model
ollama pull nomic-embed-text-v2-moe
```

Without an embedding server, codelibrarian still works — it falls back to full-text search only.

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for a step-by-step walkthrough.

```bash
cd /path/to/your/project

# Initialize the index
codelibrarian init

# Index the codebase
codelibrarian index

# Search for code
codelibrarian search "parse configuration file"

# Look up a specific symbol
codelibrarian lookup MyClass.my_method

# Check index statistics
codelibrarian status
```

## MCP Server

Codelibrarian exposes an MCP server so LLM clients (Claude Desktop, Claude Code, etc.) can query your codebase directly.

```bash
codelibrarian serve
```

The server runs on stdio and provides these tools:

| Tool | Description |
|------|-------------|
| `search_code` | Hybrid semantic + full-text search across all symbols |
| `lookup_symbol` | Look up a symbol by exact or qualified name |
| `get_callers` | Find all callers of a function/method (recursive) |
| `get_callees` | Find all functions called by a symbol (recursive) |
| `count_callers` | Return the number of direct callers (efficient for UI) |
| `count_callees` | Return the number of direct callees (efficient for UI) |
| `get_file_imports` | Show a file's imports and reverse imports |
| `list_symbols` | Filter symbols by kind, name pattern, or file |
| `get_class_hierarchy` | Get inheritance tree for a class |
| `generate_class_diagram` | Generate a Mermaid class hierarchy diagram |
| `generate_call_graph` | Generate a Mermaid call graph diagram |
| `generate_import_graph` | Generate a Mermaid module import dependency diagram |

### Claude Desktop Configuration

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "codelibrarian": {
      "command": "codelibrarian",
      "args": ["serve", "--path", "/path/to/your/project"]
    }
  }
}
```

## CLI Reference

```
codelibrarian init [--path DIR]
    Create .codelibrarian/ directory with default config and database.

codelibrarian index [--full] [--reembed] [--files FILE...] [--path DIR]
    Index the codebase. By default, skips unchanged files.
    --full       Reindex all files, ignoring hash cache.
    --reembed    Regenerate all embeddings.
    --files      Index only specific files (used by git hooks).

codelibrarian search QUERY [--limit N] [--semantic-only] [--text-only] [--path DIR]
    Search the index with natural language or keywords.

codelibrarian lookup NAME [--path DIR]
    Show full details for a symbol by name or qualified name.

codelibrarian callers NAME [--depth N] [--path DIR]
    Find all functions/methods that call the named symbol.

codelibrarian callees NAME [--depth N] [--path DIR]
    Find all functions/methods called by the named symbol.

codelibrarian status [--path DIR]
    Display index statistics (files, symbols by kind, embeddings).

codelibrarian hooks install [--path DIR]
    Install git post-commit and post-merge hooks for automatic
    incremental reindexing after each commit.

codelibrarian diagram class NAME [--path DIR]
    Generate a Mermaid class hierarchy diagram.

codelibrarian diagram calls NAME [--depth N] [--direction callees|callers] [--path DIR]
    Generate a Mermaid call graph diagram.

codelibrarian diagram imports [--file PATH] [--path DIR]
    Generate a Mermaid module import dependency diagram.

codelibrarian serve [--path DIR]
    Start the MCP server on stdio.
```

## Configuration

After `codelibrarian init`, edit `.codelibrarian/config.toml`:

```toml
[index]
root = "."
exclude = [
    "node_modules/",
    ".git/",
    "__pycache__/",
    "dist/",
    "build/",
    ".codelibrarian/",
    "*.min.js",
]
languages = ["python", "typescript", "javascript", "rust", "java", "cpp", "swift", "kotlin"]

[embeddings]
api_url    = "http://localhost:11434/v1/embeddings"  # Ollama default
model      = "nomic-embed-text-v2-moe"
dimensions = 768
batch_size = 32
max_chars  = 1600   # ~400 tokens per symbol
enabled    = true    # Set to false to disable semantic search entirely

[database]
path = ".codelibrarian/index.db"
```

The `api_url` accepts any OpenAI-compatible embedding endpoint — Ollama, vLLM, LiteLLM, OpenAI, etc.

## VS Code Extension

The `vscode-extension/` directory contains a VS Code extension that provides a rich UI on top of the codelibrarian index.

### Features

- **MCP auto-discovery** — The extension registers the MCP server with VS Code's built-in MCP support, so GitHub Copilot Chat and Claude Code can use all codelibrarian tools automatically with zero configuration.
- **CodeLens annotations** — Inline caller counts above every function, method, and class. Click to open the call graph.
- **Symbol search** — A quick-pick (`Ctrl+Shift+P` → "Codelibrarian: Search Symbols") with debounced hybrid search and click-to-navigate.
- **Call graph tree view** — An Explorer sidebar panel showing callers and callees of any symbol, expandable to multiple hops.
- **Auto-index on save** — Changed files are re-indexed automatically when saved (2-second debounce).
- **Status bar** — Shows connection state to the codelibrarian MCP server.

### Install from Source

Requires Node.js 18+ and the `codelibrarian` CLI already installed.

```bash
cd vscode-extension
npm install
npm run compile
```

Then press `F5` in VS Code to launch the Extension Development Host, or package a `.vsix`:

```bash
npx vsce package
code --install-extension codelibrarian-vscode-0.1.0.vsix
```

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `codelibrarian.executablePath` | `"codelibrarian"` | Path to the codelibrarian binary |
| `codelibrarian.autoIndexOnSave` | `true` | Re-index files on save |
| `codelibrarian.codeLensEnabled` | `true` | Show caller counts above symbols |
| `codelibrarian.searchResultLimit` | `20` | Max results in symbol search |

### Architecture

The extension spawns `codelibrarian serve` as a child process and communicates over the MCP stdio protocol using `@modelcontextprotocol/sdk`. A supervisor handles crash recovery with exponential back-off. The extension requires a project that has been initialized with `codelibrarian init` — if the `.codelibrarian/` directory is missing, it offers to initialize.

## Git Hooks

Install hooks to keep the index up to date automatically:

```bash
codelibrarian hooks install
```

This installs `post-commit` and `post-merge` hooks that run `codelibrarian index --files <changed>` in the background after each commit or merge.

## License

AGPL 3.0 — see [LICENSE](LICENSE).
