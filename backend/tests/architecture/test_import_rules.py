"""Module boundaries are enforced by a test, not by discipline.

Rules from AGENTS.md: modules talk only through the other module's service.py,
and the dependency direction is analysis -> (cvs, jobs).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

MODULES_DIR = Path(__file__).resolve().parents[2] / "app" / "modules"
ALLOWED_EDGES = {("analysis", "cvs"), ("analysis", "jobs")}


def _module_packages() -> list[str]:
    return sorted(path.name for path in MODULES_DIR.iterdir() if path.is_dir())


def _imported_modules(tree: ast.Module) -> set[str]:
    """Module-level imports, ignoring the type-checking-only block."""
    names: set[str] = set()
    for node in _runtime_nodes(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _runtime_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Walk the tree but skip everything under `if TYPE_CHECKING:`."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.If) and _is_type_checking(child.test):
            continue
        yield child
        yield from _runtime_nodes(child)


def _is_type_checking(test: ast.expr) -> bool:
    return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"


def _python_files(package: str) -> list[Path]:
    return sorted((MODULES_DIR / package).rglob("*.py"))


@pytest.mark.parametrize("package", _module_packages())
def test_cross_module_imports_go_through_service(package: str) -> None:
    violations: list[str] = []
    for path in _python_files(package):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for imported in _imported_modules(tree):
            parts = imported.split(".")
            if parts[:2] != ["app", "modules"] or len(parts) < 3:
                continue
            target = parts[2]
            if target == package:
                continue
            if (package, target) not in ALLOWED_EDGES or len(parts) == 3 or parts[3] != "service":
                violations.append(f"{path.parent.name}/{path.name} imports {imported}")
    assert not violations, "Forbidden cross-module imports:\n" + "\n".join(violations)


@pytest.mark.parametrize("package", _module_packages())
def test_modules_do_not_import_the_container(package: str) -> None:
    offenders = [
        path.name
        for path in _python_files(package)
        if "app.container" in _imported_modules(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not offenders, f"{package} must not import app.container: {offenders}"
