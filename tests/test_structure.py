"""Tier rules: every module declares MATURITY; stable/incubating code never imports lab."""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "memvid_guardrail"
TIERS = {"stable", "incubating", "lab"}


def modules():
    return [p for p in PKG.rglob("*.py") if p.name != "__init__.py"]


def maturity(path: Path) -> str | None:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "MATURITY" for t in node.targets):
            return node.value.value
    return None


def test_every_module_declares_a_tier():
    missing = {str(p.relative_to(PKG)): maturity(p) for p in modules() if maturity(p) not in TIERS}
    assert not missing


def test_lab_modules_live_in_lab_and_say_so():
    for path in modules():
        in_lab = "lab" in path.relative_to(PKG).parts
        assert (maturity(path) == "lab") == in_lab, path


def test_non_lab_code_never_imports_lab():
    offenders = []
    for path in modules():
        if "lab" in path.relative_to(PKG).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            if any(n.startswith("memvid_guardrail.lab") for n in names):
                offenders.append(str(path.relative_to(PKG)))
    assert not offenders


def test_core_has_no_third_party_imports():
    allowed = {"__future__", "dataclasses", "enum", "hashlib", "typing"}
    for path in (PKG / "core").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] in allowed, (path.name, node.module)
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in allowed for a in node.names), path.name
