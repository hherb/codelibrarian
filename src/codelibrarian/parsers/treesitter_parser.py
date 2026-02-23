"""tree-sitter based parser for TypeScript, JavaScript, Rust, Java, C++.

Uses the tree-sitter 0.23+ API where language packages expose a language()
callable and the Parser takes a Language object directly.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tree_sitter import Language, Node, Parser

from codelibrarian.models import GraphEdges, Parameter, ParseResult, Symbol
from codelibrarian.parsers.base import BaseParser


# --------------------------------------------------------------------------- #
# Language loader cache
# --------------------------------------------------------------------------- #

_LANGUAGE_CACHE: dict[str, Language] = {}


def _load_language(lang: str) -> Language | None:
    if lang in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[lang]

    try:
        if lang == "typescript":
            import tree_sitter_typescript as mod
            language = Language(mod.language_typescript())
        elif lang == "javascript":
            import tree_sitter_javascript as mod
            language = Language(mod.language())
        elif lang == "rust":
            import tree_sitter_rust as mod
            language = Language(mod.language())
        elif lang == "java":
            import tree_sitter_java as mod
            language = Language(mod.language())
        elif lang == "cpp":
            try:
                import tree_sitter_cpp as mod
                language = Language(mod.language())
            except ImportError:
                return None
        elif lang == "swift":
            import tree_sitter_swift as mod
            language = Language(mod.language())
        elif lang == "kotlin":
            import tree_sitter_kotlin as mod
            language = Language(mod.language())
        else:
            return None

        _LANGUAGE_CACHE[lang] = language
        return language
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Node text helpers
# --------------------------------------------------------------------------- #

def _text(node: Node, source: bytes) -> str:
    """Return the UTF-8 source text spanned by *node*."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _child_by_type(node: Node, *types: str) -> Node | None:
    """Return the first direct child whose type is one of *types*, or None."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _children_by_type(node: Node, *types: str) -> list[Node]:
    """Return all direct children whose type is one of *types*."""
    return [c for c in node.children if c.type in types]


def _first_named_child(node: Node) -> Node | None:
    """Return the first named (non-anonymous) direct child, or None."""
    for child in node.children:
        if child.is_named:
            return child
    return None


# --------------------------------------------------------------------------- #
# Docstring extraction heuristic (comment block before/after node)
# --------------------------------------------------------------------------- #

def _extract_docstring(node: Node, source: bytes) -> str:
    """Extract leading string literal or JSDoc comment from a node."""
    # For functions/classes: look for a block_comment or string immediately
    # after the opening brace or as the first statement.
    for child in node.children:
        if child.type in ("block_comment", "line_comment"):
            text = _text(child, source).strip()
            # Strip // and /* */ markers
            text = re.sub(r"^/\*+\s*", "", text)
            text = re.sub(r"\s*\*+/$", "", text)
            text = re.sub(r"^\s*\*\s?", "", text, flags=re.MULTILINE)
            text = re.sub(r"^//\s?", "", text, flags=re.MULTILINE)
            return text.strip()
        if child.type in ("string", "string_literal", "raw_string_literal",
                          "template_string", "expression_statement"):
            # Could be a docstring literal
            break
    return ""


# --------------------------------------------------------------------------- #
# Per-language extractors
# --------------------------------------------------------------------------- #

class _TSExtractor:
    """Extracts symbols from TypeScript/JavaScript tree-sitter trees."""

    def __init__(self, source: bytes, module_name: str, lang: str):
        self.source = source
        self.module_name = module_name
        self.lang = lang
        self.symbols: list[Symbol] = []
        self.edges = GraphEdges()
        self._class_stack: list[str] = []

    def extract(self, tree_root: Node) -> None:
        self._walk(tree_root)

    def _walk(self, node: Node) -> None:
        if node.type in ("class_declaration", "class_expression"):
            self._handle_class(node)
        elif node.type in (
            "function_declaration",
            "function_expression",
            "arrow_function",
            "method_definition",
            "generator_function_declaration",
        ):
            self._handle_function(node)
        elif node.type == "import_statement":
            self._handle_import(node)
        elif node.type == "call_expression":
            self._handle_call(node)
        else:
            for child in node.children:
                self._walk(child)

    def _qualify(self, name: str) -> str:
        if self._class_stack:
            return f"{self._class_stack[-1]}.{name}"
        return f"{self.module_name}.{name}"

    def _handle_class(self, node: Node) -> None:
        name_node = _child_by_type(node, "type_identifier", "identifier")
        if not name_node:
            return
        name = _text(name_node, self.source)
        qualified = self._qualify(name)
        parent_qn = self._class_stack[-1] if self._class_stack else None

        # Heritage (extends/implements)
        heritage = _child_by_type(node, "class_heritage")
        bases = []
        sig = f"class {name}"
        if heritage:
            heritage_text = _text(heritage, self.source)
            sig = f"class {name} {heritage_text}"
            for hc in heritage.children:
                if hc.type == "extends_clause":
                    for base_node in hc.children:
                        if base_node.type in ("identifier", "member_expression"):
                            bases.append(_text(base_node, self.source))

        doc = _extract_docstring(node, self.source)
        sym = Symbol(
            name=name,
            qualified_name=qualified,
            kind="class",
            file_path="",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            docstring=doc,
            parent_qualified_name=parent_qn,
        )
        self.symbols.append(sym)
        for base in bases:
            self.edges.inherits.append((qualified, base))

        self._class_stack.append(qualified)
        body = _child_by_type(node, "class_body")
        if body:
            for child in body.children:
                self._walk(child)
        self._class_stack.pop()

    def _handle_function(self, node: Node) -> None:
        # Get name
        name_node = _child_by_type(node, "identifier", "property_identifier")
        if not name_node:
            # Arrow functions assigned to variables handled by parent
            return
        name = _text(name_node, self.source)
        if not name:
            return

        kind = "method" if self._class_stack else "function"
        qualified = self._qualify(name)
        parent_qn = self._class_stack[-1] if self._class_stack else None

        params = self._extract_params(node)
        return_type = self._extract_return_type(node)
        sig = self._build_sig(node, name, params, return_type)
        doc = _extract_docstring(node, self.source)

        sym = Symbol(
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path="",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            docstring=doc,
            parameters=params,
            return_type=return_type,
            parent_qualified_name=parent_qn,
        )
        self.symbols.append(sym)

        # Walk body for nested calls/classes/functions
        body = _child_by_type(node, "statement_block")
        if body:
            for child in body.children:
                self._walk(child)

    def _handle_import(self, node: Node) -> None:
        source_node = _child_by_type(node, "string")
        if not source_node:
            return
        module = _text(source_node, self.source).strip("'\"")
        # Import clause
        clause = _child_by_type(node, "import_clause")
        if clause:
            for child in clause.children:
                if child.type == "named_imports":
                    for spec in child.children:
                        if spec.type == "import_specifier":
                            name_node = _first_named_child(spec)
                            if name_node:
                                self.edges.imports.append(
                                    (self.module_name, module, _text(name_node, self.source))
                                )
                elif child.type == "identifier":
                    self.edges.imports.append(
                        (self.module_name, module, _text(child, self.source))
                    )
        else:
            self.edges.imports.append((self.module_name, module, None))

    def _handle_call(self, node: Node) -> None:
        func_node = _child_by_type(node, "identifier", "member_expression")
        if func_node:
            name = _text(func_node, self.source)
            # Only record simple names, not very long member expressions
            if len(name) <= 100:
                parent_qn = self._class_stack[-1] if self._class_stack else (
                    f"{self.module_name}.<top>"
                )
                self.edges.calls.append((parent_qn, name))
        for child in node.children:
            if child.type not in ("identifier", "member_expression"):
                self._walk(child)

    def _extract_params(self, node: Node) -> list[Parameter]:
        params = []
        param_list = _child_by_type(node, "formal_parameters")
        if not param_list:
            return params
        for child in param_list.children:
            if child.type in ("identifier", "required_parameter", "optional_parameter",
                               "rest_pattern", "assignment_pattern"):
                param = self._parse_param(child)
                if param:
                    params.append(param)
        return params

    def _parse_param(self, node: Node) -> Parameter | None:
        if node.type == "identifier":
            return Parameter(name=_text(node, self.source))
        name_node = _child_by_type(node, "identifier", "rest_pattern")
        if not name_node:
            return None
        name = _text(name_node, self.source)
        type_node = _child_by_type(node, "type_annotation")
        type_str = None
        if type_node:
            type_str = _text(type_node, self.source).lstrip(":").strip()
        return Parameter(name=name, type=type_str)

    def _extract_return_type(self, node: Node) -> str | None:
        type_node = _child_by_type(node, "type_annotation")
        if type_node:
            return _text(type_node, self.source).lstrip(":").strip()
        return None

    def _build_sig(
        self,
        node: Node,
        name: str,
        params: list[Parameter],
        return_type: str | None,
    ) -> str:
        prefix = "async " if any(c.type == "async" for c in node.children) else ""
        param_strs = []
        for p in params:
            s = p.name
            if p.type:
                s += f": {p.type}"
            if p.default is not None:
                s += f" = {p.default}"
            param_strs.append(s)
        sig = f"{prefix}function {name}({', '.join(param_strs)})"
        if return_type:
            sig += f": {return_type}"
        return sig


class _RustExtractor:
    """Extracts functions, structs, enums, traits and impl blocks from Rust source."""

    def __init__(self, source: bytes, module_name: str):
        self.source = source
        self.module_name = module_name
        self.symbols: list[Symbol] = []
        self.edges = GraphEdges()
        self._impl_stack: list[str] = []

    def extract(self, root: Node) -> None:
        self._walk(root)

    def _walk(self, node: Node) -> None:
        if node.type == "function_item":
            self._handle_fn(node)
        elif node.type in ("struct_item", "enum_item", "trait_item"):
            self._handle_type(node)
        elif node.type == "impl_item":
            self._handle_impl(node)
        elif node.type == "use_declaration":
            self._handle_use(node)
        else:
            for child in node.children:
                self._walk(child)

    def _qualify(self, name: str) -> str:
        if self._impl_stack:
            return f"{self._impl_stack[-1]}::{name}"
        return f"{self.module_name}::{name}"

    def _handle_fn(self, node: Node) -> None:
        name_node = _child_by_type(node, "identifier")
        if not name_node:
            return
        name = _text(name_node, self.source)
        qualified = self._qualify(name)
        kind = "method" if self._impl_stack else "function"

        params = self._extract_params(node)
        return_type = self._extract_return_type(node)
        sig = _text(node, self.source).split("{")[0].strip()
        doc = self._extract_doc_comment(node)

        sym = Symbol(
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path="",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig[:500],
            docstring=doc,
            parameters=params,
            return_type=return_type,
            parent_qualified_name=self._impl_stack[-1] if self._impl_stack else None,
        )
        self.symbols.append(sym)

        body = _child_by_type(node, "block")
        if body:
            for child in body.children:
                self._walk(child)

    def _handle_type(self, node: Node) -> None:
        name_node = _child_by_type(node, "type_identifier")
        if not name_node:
            return
        name = _text(name_node, self.source)
        qualified = f"{self.module_name}::{name}"
        sig = f"{node.type.replace('_item', '')} {name}"
        doc = self._extract_doc_comment(node)
        sym = Symbol(
            name=name,
            qualified_name=qualified,
            kind="class",
            file_path="",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            docstring=doc,
        )
        self.symbols.append(sym)
        for child in node.children:
            self._walk(child)

    def _handle_impl(self, node: Node) -> None:
        type_node = _child_by_type(node, "type_identifier")
        if not type_node:
            return
        type_name = _text(type_node, self.source)
        qualified = f"{self.module_name}::{type_name}"
        self._impl_stack.append(qualified)
        for child in node.children:
            self._walk(child)
        self._impl_stack.pop()

    def _handle_use(self, node: Node) -> None:
        path_text = _text(node, self.source)
        # Strip leading "use " keyword and trailing semicolon
        path_text = path_text.strip().removeprefix("use").strip().rstrip(";")
        self.edges.imports.append((self.module_name, path_text, None))

    def _extract_params(self, node: Node) -> list[Parameter]:
        params = []
        param_list = _child_by_type(node, "parameters")
        if not param_list:
            return params
        for child in param_list.children:
            if child.type == "parameter":
                name_node = _child_by_type(child, "identifier", "pattern")
                type_node = _child_by_type(child, "type_identifier", "reference_type",
                                           "generic_type", "scoped_type_identifier")
                name = _text(name_node, self.source) if name_node else "?"
                type_str = _text(type_node, self.source) if type_node else None
                params.append(Parameter(name=name, type=type_str))
            elif child.type == "self_parameter":
                params.append(Parameter(name="self"))
        return params

    def _extract_return_type(self, node: Node) -> str | None:
        ret = _child_by_type(node, "return_type")
        if ret:
            # Skip the "->" token
            for child in ret.children:
                if child.type != "->":
                    return _text(child, self.source)
        return None

    def _extract_doc_comment(self, node: Node) -> str:
        # Look for preceding sibling line_comment nodes
        parent = node.parent
        if not parent:
            return ""
        lines = []
        for child in parent.children:
            if child == node:
                break
            if child.type == "line_comment":
                text = _text(child, self.source).lstrip("/").lstrip("!").strip()
                lines.append(text)
            else:
                lines = []  # Reset if there's a gap
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Generic Java / C++ extractor (simplified)
# --------------------------------------------------------------------------- #

class _GenericExtractor:
    """Minimal extractor for Java and C++ - classes and methods only."""

    def __init__(self, source: bytes, module_name: str, lang: str):
        self.source = source
        self.module_name = module_name
        self.lang = lang
        self.symbols: list[Symbol] = []
        self.edges = GraphEdges()
        self._class_stack: list[str] = []

    def extract(self, root: Node) -> None:
        self._walk(root)

    def _walk(self, node: Node) -> None:
        if node.type in (
            "class_declaration",
            "interface_declaration",
            "class_specifier",
            "struct_specifier",
        ):
            self._handle_class(node)
        elif node.type in (
            "method_declaration",
            "function_definition",
            "constructor_declaration",
        ):
            self._handle_method(node)
        else:
            for child in node.children:
                self._walk(child)

    def _qualify(self, name: str) -> str:
        if self._class_stack:
            return f"{self._class_stack[-1]}.{name}"
        return f"{self.module_name}.{name}"

    def _handle_class(self, node: Node) -> None:
        name_node = _child_by_type(node, "identifier", "type_identifier")
        if not name_node:
            return
        name = _text(name_node, self.source)
        qualified = self._qualify(name)
        sig = f"class {name}"
        sym = Symbol(
            name=name,
            qualified_name=qualified,
            kind="class",
            file_path="",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
        )
        self.symbols.append(sym)
        self._class_stack.append(qualified)
        for child in node.children:
            self._walk(child)
        self._class_stack.pop()

    def _handle_method(self, node: Node) -> None:
        name_node = _child_by_type(node, "identifier")
        if not name_node:
            return
        name = _text(name_node, self.source)
        kind = "method" if self._class_stack else "function"
        qualified = self._qualify(name)
        sig = _text(node, self.source).split("{")[0].strip()[:300]
        sym = Symbol(
            name=name,
            qualified_name=qualified,
            kind=kind,
            file_path="",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            parent_qualified_name=self._class_stack[-1] if self._class_stack else None,
        )
        self.symbols.append(sym)
        for child in node.children:
            self._walk(child)


# --------------------------------------------------------------------------- #
# Main parser class
# --------------------------------------------------------------------------- #

class TreeSitterParser(BaseParser):
    def parse(self, file_path: Path, source: str, module_name: str) -> ParseResult:
        lang = self._detect_lang(file_path)
        if not lang:
            return ParseResult(symbols=[], edges=GraphEdges())

        language = _load_language(lang)
        if language is None:
            return ParseResult(symbols=[], edges=GraphEdges())

        try:
            parser = Parser(language)
            source_bytes = source.encode("utf-8", errors="replace")
            tree = parser.parse(source_bytes)
        except Exception:
            return ParseResult(symbols=[], edges=GraphEdges())

        if lang in ("typescript", "javascript"):
            extractor = _TSExtractor(source_bytes, module_name, lang)
            extractor.extract(tree.root_node)
        elif lang == "rust":
            extractor = _RustExtractor(source_bytes, module_name)
            extractor.extract(tree.root_node)
        else:
            extractor = _GenericExtractor(source_bytes, module_name, lang)
            extractor.extract(tree.root_node)

        return ParseResult(symbols=extractor.symbols, edges=extractor.edges)

    @staticmethod
    def _detect_lang(file_path: Path) -> str | None:
        ext_map = {
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "cpp",
            ".h": "cpp",
            ".hpp": "cpp",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
        }
        return ext_map.get(file_path.suffix.lower())
