"""Tests for the Kotlin tree-sitter parser."""

from pathlib import Path

import pytest

from codelibrarian.parsers.treesitter_parser import TreeSitterParser

FIXTURES = Path(__file__).parent / "fixtures"
KOTLIN_SAMPLE = FIXTURES / "kotlin_sample" / "Models.kt"


@pytest.fixture
def kotlin_result():
    try:
        import tree_sitter_kotlin  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-kotlin not installed")
    parser = TreeSitterParser()
    source = KOTLIN_SAMPLE.read_text()
    return parser.parse(KOTLIN_SAMPLE, source, "Models")


def test_kotlin_finds_classes(kotlin_result):
    class_names = {s.name for s in kotlin_result.symbols if s.kind == "class"}
    assert "Animal" in class_names
    assert "Dog" in class_names
    assert "PetRecord" in class_names  # data class
    assert "Color" in class_names  # enum class


def test_kotlin_finds_sealed_class(kotlin_result):
    class_names = {s.name for s in kotlin_result.symbols if s.kind == "class"}
    assert "Result" in class_names


def test_kotlin_finds_interface(kotlin_result):
    class_names = {s.name for s in kotlin_result.symbols if s.kind == "class"}
    assert "Greetable" in class_names


def test_kotlin_finds_object(kotlin_result):
    class_names = {s.name for s in kotlin_result.symbols if s.kind == "class"}
    assert "PetRegistry" in class_names


def test_kotlin_finds_methods(kotlin_result):
    method_names = {s.name for s in kotlin_result.symbols if s.kind == "method"}
    assert "speak" in method_names
    assert "fetch" in method_names
    assert "isAdopted" in method_names


def test_kotlin_finds_functions(kotlin_result):
    func_names = {s.name for s in kotlin_result.symbols if s.kind == "function"}
    assert "findOldest" in func_names
    assert "fetchAnimals" in func_names


def test_kotlin_qualified_names(kotlin_result):
    qnames = {s.qualified_name for s in kotlin_result.symbols}
    assert "com.example.models.Animal" in qnames
    assert "com.example.models.Animal.speak" in qnames
    assert "com.example.models.Dog.fetch" in qnames
    assert "com.example.models.findOldest" in qnames


def test_kotlin_parameters(kotlin_result):
    fetch = next(s for s in kotlin_result.symbols if s.qualified_name == "com.example.models.Dog.fetch")
    param_names = [p.name for p in fetch.parameters]
    assert "item" in param_names
    param_types = [p.type for p in fetch.parameters]
    assert "String" in param_types


def test_kotlin_return_type(kotlin_result):
    fetch = next(s for s in kotlin_result.symbols if s.qualified_name == "com.example.models.Dog.fetch")
    assert fetch.return_type == "String"


def test_kotlin_docstring(kotlin_result):
    animal = next(s for s in kotlin_result.symbols if s.name == "Animal")
    assert "animal" in animal.docstring.lower() or "base" in animal.docstring.lower()


def test_kotlin_inheritance_edges(kotlin_result):
    inherits = kotlin_result.edges.inherits
    child_names = {edge[0] for edge in inherits}
    assert any("Dog" in name for name in child_names)


def test_kotlin_import_edges(kotlin_result):
    modules = {edge[1] for edge in kotlin_result.edges.imports}
    assert "java.util.UUID" in modules
    assert "kotlinx.serialization.Serializable" in modules


def test_kotlin_suspend_in_signature(kotlin_result):
    fetch_animals = next(s for s in kotlin_result.symbols if s.name == "fetchAnimals")
    assert "suspend" in fetch_animals.signature
