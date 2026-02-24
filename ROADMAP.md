# Roadmap

Items are listed roughly in priority order within each section.

## Diagrams

- [x] Mermaid text output for class hierarchy, call graph, and module import diagrams
- [x] CLI subcommands: `diagram class`, `diagram calls`, `diagram imports`
- [x] MCP tools: `generate_class_diagram`, `generate_call_graph`, `generate_import_graph`
- [ ] SVG/PNG rendering via optional `mmdc` (mermaid-cli) integration with `--render` flag
- [ ] Self-contained HTML page generation with embedded Mermaid.js (no external dependencies)
- [ ] VS Code extension: render diagrams in a webview panel

## Parser Improvements

- [ ] Java inheritance extraction (`extends`, `implements`) in tree-sitter `_GenericExtractor`
- [ ] C++ inheritance extraction (`:` base class syntax) in tree-sitter `_GenericExtractor`
- [ ] Java `import` statement extraction
- [ ] C/C++ `#include` directive extraction

## Search & Indexing

- [ ] Configurable embedding providers (OpenAI API, local transformers)
- [ ] Incremental embedding updates (only re-embed changed symbols)
- [ ] Cross-repository search (index multiple projects into a shared DB)

## MCP & Integration

- [ ] Resource-based MCP endpoints (expose index as browsable resources)
- [ ] Prompt templates for common workflows (e.g., "explain this function in context")
