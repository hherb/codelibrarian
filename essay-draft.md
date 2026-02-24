# The Missing Library Card: Why Every Codebase Needs a Librarian

*Whether you're a human developer or an AI assistant, finding the right code at the right moment is the unsolved problem at the heart of software engineering.*

---

There's a moment every programmer knows. You're deep in a debugging session, trying to fix a function that behaves unexpectedly. You vaguely remember there's another method somewhere in the codebase — maybe three modules over — that does something relevant. You *know* it exists. You wrote it six months ago, or a colleague wrote it last week, or you saw it while scrolling through a different file. But you can't find it. So you grep, you scroll, you open tabs, you lose your train of thought. Twenty minutes later you either find it or give up and write something new that shouldn't exist.

This is not a productivity problem. It is a context problem. And context, it turns out, is the central challenge of software development in the age of large language models.

---

## The Context Crisis — For Humans and Machines Alike

We tend to think of context management as an AI problem. When you paste code into ChatGPT or Claude, you're implicitly choosing what context to provide. You make judgment calls: include this file, exclude that one, summarize this class. If you get it wrong, the AI gives you a plausible-sounding but subtly wrong answer, because it didn't know about the interface your function is supposed to implement, or the singleton that manages global state, or the decorator that changes everything.

But humans face the same problem, just at a different scale. The human brain is a powerful inference engine, but it's not a searchable database. We lose track of code we didn't write. We forget code we did write. We misremember how things connect. The larger the codebase, the worse it gets.

The solutions available today are insufficient:

- **Grep and text search** find exact strings, not meaning. You search for "authentication" and miss the `verify_token` method that's doing the actual work.
- **IDE "Find Usages"** is excellent within a file or module, but doesn't answer natural language questions and can't reason about semantic similarity.
- **RAG pipelines stuffed with source files** work at small scale but collapse under the combinatorial weight of large codebases — either the context window fills with noise, or you pay a fortune in tokens for diminishing returns.
- **GitHub Copilot and similar tools** index your code, but the index serves their system, not yours. You can't query it directly, inspect it, or integrate it into your own workflows.

The result is that developers — human and AI — spend enormous energy on a problem that should have been solved: *finding the right code to read before you write new code*.

---

## Enter the Librarian

A library without a catalogue is just a room full of books. You could still find things in it — if you were willing to read every shelf. A good cataloguing system changes the relationship between a reader and a collection. It makes the collection queryable.

[Codelibrarian](https://github.com/hherb/codelibrarian) applies this principle to software. It is a self-maintaining code index — a catalogue, not a search engine. The distinction matters. A search engine finds text. A catalogue understands structure.

When you run `codelibrarian index` on a project, it does something more interesting than string matching. It parses your source files at the AST level (using Python's native `ast` module for Python, and tree-sitter grammars for TypeScript, JavaScript, Rust, Java, C/C++, Swift, and Kotlin). It extracts:

- Every function, method, class, and module — with full signatures, parameters, return types, docstrings, and decorators
- Every call relationship — which function calls which, recursively traversable to arbitrary depth
- Every inheritance relationship — the full class hierarchy
- Every import dependency — what each file imports and what imports it

All of this goes into a SQLite database. Not a remote service. Not a proprietary cloud. A local file in your project directory. You own the index.

---

## Hybrid Search: When Keywords Aren't Enough

The index is only as useful as the query interface. Codelibrarian supports two complementary search modes:

**BM25 full-text search** via SQLite's FTS5 virtual table. Fast, precise, no external dependencies. Type a keyword, get ranked results.

**Semantic vector search** via an embedding model (by default, Ollama running locally). This is where it gets interesting. When you ask "find functions that handle authentication failures," codelibrarian doesn't look for those exact words. It converts your query to a vector in the same embedding space as all the indexed symbols, and returns whatever is geometrically nearest — regardless of what it's called.

These two modes are combined into a hybrid score that favors results that are both lexically relevant and semantically close. The result is search that behaves more like a knowledgeable colleague than a grep command.

And if you don't have an embedding server? Codelibrarian falls back to text-only search gracefully. No breakage, no configuration required. The system degrades predictably.

---

## The Graph: Understanding Code as a Network

Here's where codelibrarian departs from most code search tools. It doesn't just index what code *is*. It indexes how code *connects*.

Every function call is recorded as a directed edge. Every inheritance relationship is an edge. Every import is an edge. The result is a queryable graph that answers questions like:

- *What calls `process_payment`?* (callers, recursively)
- *What does `validate_order` depend on?* (callees, recursively)
- *What is the full class hierarchy of `BaseHandler`?*
- *What files does `src/api/routes.py` import, and what imports it?*

These are not questions that text search can answer. They require understanding structure. And they're exactly the questions you need to answer before safely modifying or extending existing code.

The call graph is also smart about noise. Parser-time filtering removes calls to builtins, standard library functions, and external dependencies. Only project-internal calls appear in the graph. This is the difference between a graph that's useful and a graph that's overwhelming.

---

## The MCP Server: Giving LLMs a Library Card

The Model Context Protocol (MCP) is an emerging standard for giving LLM-based tools structured access to external data and capabilities. Codelibrarian implements an MCP server that exposes the full index to any MCP-compatible client — Claude Desktop, Claude Code, GitHub Copilot, or any agent you build yourself.

This is the key insight about the token economy: **the best context is surgical context**.

When an LLM is trying to help you modify a function, it doesn't need to read your entire codebase. It needs:
1. The function itself
2. Its callers (so it doesn't break the interface)
3. Its callees (so it understands what it depends on)
4. Semantically similar functions (for consistency)

A naive RAG approach might embed and retrieve random chunks of source files, potentially stuffing the context window with irrelevant code from distant modules. Codelibrarian's approach is different: the LLM calls specific tools — `get_callers`, `get_callees`, `search_code`, `get_class_hierarchy` — and gets back exactly what it needs, in structured form, with file locations and line numbers.

The savings compound. Less irrelevant context means:
- Fewer tokens consumed (direct cost reduction)
- Less noise for the model to reason through (better answers)
- More room in the context window for the actual task (higher quality output)
- Fewer round-trips needed because the first answer is more likely to be right

In practice, this means the difference between an AI assistant that says "I'd need to see more of your codebase to answer this" and one that says "Here's the fix — and here are the three call sites you'll need to update."

---

## Self-Maintenance: The Index That Keeps Itself Current

A code index that goes stale is worse than no index. You start trusting it, then you get burned by outdated information.

Codelibrarian solves this through two mechanisms:

**Incremental indexing.** Every file is tracked by its SHA256 hash. When you re-run `codelibrarian index`, only modified files are re-parsed and re-embedded. A large project that takes 30 seconds to index from scratch might take under a second to update after a small change.

**Git hooks.** Run `codelibrarian hooks install` and the index updates automatically after every commit and merge, running in the background on only the files that changed. You don't think about it. The index is always current.

The VS Code extension adds a third layer: auto-indexing on save, with a 2-second debounce. Your index updates as you work, not just when you commit.

---

## The VS Code Extension: Context at a Glance

The VS Code extension turns the index into a visual layer over your code:

**CodeLens annotations** show caller counts inline above every function, method, and class. At a glance, you know whether a function is called once (safe to refactor aggressively) or fifty times (touch with extreme care). Click the count to open the call graph.

**Symbol search** provides a fuzzy-searchable quick-pick of everything in the index, with hybrid search and click-to-navigate. It's the Ctrl+P of your codebase structure, not just your file names.

**The call graph tree view** lets you explore callers and callees of any symbol, expanding to multiple hops. It's the kind of view that used to require a dedicated code analysis tool, now available in your sidebar.

**MCP auto-discovery** registers the codelibrarian MCP server with VS Code's built-in MCP support, so GitHub Copilot Chat and Claude Code automatically gain access to all codelibrarian tools with zero additional configuration.

---

## Local, Private, Owned

One detail worth making explicit: codelibrarian runs entirely on your machine. The index is a SQLite file. The embedding model runs locally via Ollama (or any OpenAI-compatible endpoint you control). Nothing about your codebase leaves your environment unless you choose to send it somewhere.

For many developers working on proprietary codebases, this is not a minor point. It's a requirement. The alternative — sending source code to a cloud indexing service — is simply not acceptable for a large class of real-world projects. Codelibrarian is designed for that world.

---

## What This Changes

The frustrating thing about the context problem is that it's been normalized. We've accepted that finding relevant code takes time, that LLM assistants need to be carefully hand-fed context, that working in large codebases means living with partial understanding. These aren't laws of nature. They're engineering gaps.

Codelibrarian doesn't claim to solve software engineering. It claims something more modest and more useful: that developers — human and AI — should have a structured, queryable, always-current understanding of the codebase they're working in, at the level of individual symbols and their relationships, available locally, at any moment, for free.

A library isn't useful because it has a lot of books. It's useful because it's organized.

Your codebase has a lot of code. It should be organized too.

---

*Codelibrarian is open source under the AGPL 3.0 license. Get it at [github.com/hherb/codelibrarian](https://github.com/hherb/codelibrarian).*
