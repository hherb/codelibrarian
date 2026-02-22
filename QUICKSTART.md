# Quick Start Guide

This guide walks you through indexing a project and running your first queries.

## 1. Install Codelibrarian

You need [uv](https://docs.astral.sh/uv/) installed. Then:

```bash
git clone https://github.com/hherb/codelibrarian.git
cd codelibrarian
uv tool install .
```

This installs the `codelibrarian` command on your PATH. It uses uv's managed Python which includes the SQLite extension support that codelibrarian requires.

For development, use `uv sync` and prefix commands with `uv run`:

```bash
uv sync
uv run codelibrarian --help
```

## 2. (Optional) Set Up Semantic Search

Codelibrarian works without an embedding server — it uses full-text search by default. For better results with natural language queries, install [Ollama](https://ollama.com) and pull the embedding model:

```bash
ollama pull nomic-embed-text-v2-moe
```

Make sure Ollama is running before indexing. If it's not available, codelibrarian will print a warning and continue with text-only search.

## 3. Initialize Your Project

Navigate to the project you want to index:

```bash
cd /path/to/your/project
codelibrarian init
```

This creates a `.codelibrarian/` directory containing:
- `config.toml` — configuration file (exclude patterns, embedding settings, etc.)
- `index.db` — SQLite database (created during indexing)

Add `.codelibrarian/` to your `.gitignore` if desired.

## 4. Index the Codebase

```bash
codelibrarian index
```

You'll see progress output as files are discovered, parsed, and embedded. Example:

```
  Discovered 142 files
  Indexed src/auth/handler.py (12 symbols)
  Indexed src/auth/middleware.py (5 symbols)
  ...
  Embedding batch 1/3 (32 symbols)
  Embedding batch 2/3 (32 symbols)
  Embedding batch 3/3 (18 symbols)

Index complete: 142 files scanned, 140 indexed, 2 skipped, 487 symbols, 487 embeddings
```

Subsequent runs are incremental — only changed files get re-indexed.

## 5. Search Your Code

### Natural language search

```bash
codelibrarian search "handle user authentication"
```

```
 Score  Kind      Symbol                                    Location
--------------------------------------------------------------------------------
 0.847  function  auth.handler.authenticate_user             src/auth/handler.py:23
 0.791  method    auth.middleware.AuthMiddleware.verify_token src/auth/middleware.py:45
 0.683  class     auth.models.UserSession                    src/auth/models.py:12
```

### Keyword search (no embedding server needed)

```bash
codelibrarian search "authenticate" --text-only
```

### Limit results

```bash
codelibrarian search "database connection" --limit 5
```

## 6. Look Up Symbols

Get full details about a specific function, method, or class:

```bash
codelibrarian lookup authenticate_user
```

```
============================================================
Name:      authenticate_user
Qualified: auth.handler.authenticate_user
Kind:      function
File:      src/auth/handler.py:23-58
Signature: def authenticate_user(username: str, password: str) -> UserSession | None
Returns:   UserSession | None
Parameters:
  username: str
  password: str
Decorators: rate_limit

Docstring:
  Authenticate a user by username and password. Returns a UserSession ...
```

You can also use qualified names:

```bash
codelibrarian lookup AuthMiddleware.verify_token
```

## 7. Check Index Status

```bash
codelibrarian status
```

```
Database: /path/to/project/.codelibrarian/index.db
Files indexed:   140
Symbols:
  function        198
  method          156
  class            87
  module           46
Embeddings:      487
```

## 8. Keep the Index Updated

### Option A: Git hooks (recommended)

```bash
codelibrarian hooks install
```

After every commit or merge, changed files are re-indexed automatically in the background.

### Option B: Manual re-index

```bash
# Incremental (only changed files)
codelibrarian index

# Full re-index (all files)
codelibrarian index --full

# Re-index specific files
codelibrarian index --files src/auth/handler.py src/auth/models.py
```

## 9. Use with an LLM (MCP Server)

Start the MCP server so Claude or other LLM clients can query your codebase:

```bash
codelibrarian serve
```

For Claude Desktop, add this to your MCP configuration:

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

Once connected, the LLM can:
- **Search code** — "Find functions that handle HTTP errors"
- **Look up symbols** — "Show me the signature of `DatabasePool.acquire`"
- **Trace call graphs** — "What calls `validate_input`?" / "What does `process_order` call?"
- **Explore imports** — "What does `src/api/routes.py` import?"
- **Browse structure** — "List all classes in the auth module"
- **Check inheritance** — "Show the class hierarchy for `BaseHandler`"

## 10. Customize Configuration

Edit `.codelibrarian/config.toml` to:

**Exclude directories or files:**
```toml
[index]
exclude = [
    "node_modules/",
    ".git/",
    "__pycache__/",
    "vendor/",           # add your own
    "*.generated.ts",    # glob patterns work
]
```

**Use a different embedding provider:**
```toml
[embeddings]
api_url = "https://api.openai.com/v1/embeddings"
model   = "text-embedding-3-small"
dimensions = 1536
```

**Disable embeddings entirely:**
```toml
[embeddings]
enabled = false
```

After changing config, re-index:
```bash
codelibrarian index --full
```

If you changed embedding settings, also regenerate embeddings:
```bash
codelibrarian index --full --reembed
```
