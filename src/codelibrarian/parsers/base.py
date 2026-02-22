"""Abstract base class for language parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from codelibrarian.models import ParseResult


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path, source: str, module_name: str) -> ParseResult:
        """Parse source code and return symbols + graph edges.

        Args:
            file_path: Absolute path to the file.
            source: Source code as a string.
            module_name: Dot-separated module name derived from the file path.

        Returns:
            ParseResult containing symbols and graph edges.
        """
        ...

    @staticmethod
    def derive_module_name(file_path: Path, root: Path) -> str:
        """Convert file path to dot-separated module name relative to root."""
        try:
            rel = file_path.relative_to(root)
        except ValueError:
            rel = file_path

        parts = list(rel.parts)
        if parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
            if parts[-1] == "__init__":
                parts = parts[:-1]
        elif parts:
            # Strip extension for other languages
            stem = Path(parts[-1]).stem
            parts[-1] = stem

        return ".".join(parts) if parts else file_path.stem
