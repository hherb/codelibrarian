"""Tests for the Swift tree-sitter parser."""

from pathlib import Path

import pytest

from codelibrarian.parsers.treesitter_parser import TreeSitterParser

FIXTURES = Path(__file__).parent / "fixtures"
SWIFT_SAMPLE = FIXTURES / "swift_sample" / "Models.swift"


@pytest.fixture
def swift_result():
    try:
        import tree_sitter_swift  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-swift not installed")
    parser = TreeSitterParser()
    source = SWIFT_SAMPLE.read_text()
    return parser.parse(SWIFT_SAMPLE, source, "Models")


def test_swift_finds_classes(swift_result):
    class_names = {s.name for s in swift_result.symbols if s.kind == "class"}
    assert "Animal" in class_names
    assert "Dog" in class_names
    assert "Greeting" in class_names  # struct
    assert "Color" in class_names  # enum


def test_swift_finds_protocol(swift_result):
    class_names = {s.name for s in swift_result.symbols if s.kind == "class"}
    assert "Greetable" in class_names


def test_swift_finds_methods(swift_result):
    method_names = {s.name for s in swift_result.symbols if s.kind == "method"}
    assert "speak" in method_names
    assert "fetch" in method_names
    assert "greet" in method_names


def test_swift_finds_init(swift_result):
    inits = [s for s in swift_result.symbols if s.name == "init"]
    assert len(inits) >= 2  # Animal.init and Dog.init


def test_swift_finds_functions(swift_result):
    func_names = {s.name for s in swift_result.symbols if s.kind == "function"}
    assert "findOldest" in func_names


def test_swift_qualified_names(swift_result):
    qnames = {s.qualified_name for s in swift_result.symbols}
    assert "Models.Animal" in qnames
    assert "Models.Animal.speak" in qnames
    assert "Models.Dog.fetch" in qnames
    assert "Models.findOldest" in qnames


def test_swift_parameters(swift_result):
    fetch = next(s for s in swift_result.symbols if s.qualified_name == "Models.Dog.fetch")
    param_names = [p.name for p in fetch.parameters]
    assert "item" in param_names
    param_types = [p.type for p in fetch.parameters]
    assert "String" in param_types


def test_swift_return_type(swift_result):
    fetch = next(s for s in swift_result.symbols if s.qualified_name == "Models.Dog.fetch")
    assert fetch.return_type == "String"


def test_swift_docstring(swift_result):
    animal = next(s for s in swift_result.symbols if s.name == "Animal")
    assert "base class" in animal.docstring.lower() or "animal" in animal.docstring.lower()


def test_swift_inheritance_edges(swift_result):
    inherits = swift_result.edges.inherits
    child_parent = {(edge[0], edge[1]) for edge in inherits}
    # Dog inherits Animal
    assert any("Dog" in c for c, _ in child_parent)


def test_swift_import_edges(swift_result):
    modules = {edge[1] for edge in swift_result.edges.imports}
    assert "Foundation" in modules
    assert "UIKit" in modules


def test_swift_extension_inherits(swift_result):
    """Extension conformance should create an inherits edge."""
    inherits = swift_result.edges.inherits
    # Dog: Greetable via extension
    assert any("Dog" in edge[0] and "Greetable" in edge[1] for edge in inherits)
