"""Parser factory: get the right parser for a given language."""

from __future__ import annotations

from codelibrarian.parsers.base import BaseParser
from codelibrarian.parsers.python_parser import PythonParser
from codelibrarian.parsers.treesitter_parser import TreeSitterParser

_python_parser = PythonParser()
_treesitter_parser = TreeSitterParser()


def get_parser(language: str) -> BaseParser | None:
    if language == "python":
        return _python_parser
    if language in ("typescript", "javascript", "rust", "java", "cpp"):
        return _treesitter_parser
    return None


__all__ = ["BaseParser", "PythonParser", "TreeSitterParser", "get_parser"]
