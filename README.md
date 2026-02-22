# Codelibrarian

A self-maintaining code index for LLM and human queries via MCP and CLI.

Codelibrarian indexes your codebase — functions, methods, classes, modules — and lets you search it with natural language or keywords. It builds call graphs, tracks inheritance hierarchies, and maps import dependencies. Results are available through an MCP server (for LLM clients like Claude) or a command-line interface.

## How It Works

Codelibrarian parses your source files into a SQLite database with:

- **Symbol extraction** — functions, methods, classes, and modules with full signatures, docstrings, parameters, decorators, and return types
- **Hybrid search** — combines semantic vector search (via embeddings) with BM25 full-text search for ranked results
- **Call graph** — tracks which functions call which, traversable to arbitrary depth
- **Inheritance hierarchy** — maps parent/child class relationships
- **Import graph** — shows what each file imports and what imports it
- **Incremental indexing** — only re-indexes files that have changed (SHA256 hash comparison)

## Supported Languages

| Language   | Parser     | Extensions                     |
|------------|------------|--------------------------------|
| Python     | `ast`      | `.py`                          |
| TypeScript | tree-sitter| `.ts`, `.tsx`                  |
| JavaScript | tree-sitter| `.js`, `.jsx`, `.mjs`          |
| Rust       | tree-sitter| `.rs`                          |
| Java       | tree-sitter| `.java`                        |
| C/C++      | tree-sitter| `.c`, `.h`, `.cpp`, `.cc`, `.cxx`, `.hpp` |

Python gets deeper analysis (parameter defaults, decorators, call extraction) because it uses Python's own AST module. Other languages use tree-sitter grammars.

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/hherb/codelibrarian.git
cd codelibrarian
pip install .

# Or editable install for development
pip install -e ".[dev]"

# Or using uv
uv pip install .
```

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
| `get_file_imports` | Show a file's imports and reverse imports |
| `list_symbols` | Filter symbols by kind, name pattern, or file |
| `get_class_hierarchy` | Get inheritance tree for a class |

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

codelibrarian status [--path DIR]
    Display index statistics (files, symbols by kind, embeddings).

codelibrarian hooks install [--path DIR]
    Install git post-commit and post-merge hooks for automatic
    incremental reindexing after each commit.

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
languages = ["python", "typescript", "javascript", "rust", "java", "cpp"]

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

## Git Hooks

Install hooks to keep the index up to date automatically:

```bash
codelibrarian hooks install
```

This installs `post-commit` and `post-merge` hooks that run `codelibrarian index --files <changed>` in the background after each commit or merge.

## License

Apache 2.0 — see [LICENSE](LICENSE).
