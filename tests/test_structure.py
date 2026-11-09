"""Tier rules: every module declares MATURITY; stable/incubating code never imports lab."""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "rag_research_agent"
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
        in_lab = path.parent.name == "lab"
        assert (maturity(path) == "lab") == in_lab, path


def test_non_lab_code_never_imports_lab():
    offenders = []
    for path in modules():
        if path.parent.name == "lab":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            if any(n.startswith("rag_research_agent.lab") for n in names):
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


# ---------------------------------------------------------------- P0 separability (DESIGN.ko.md 2, 3-2)
import subprocess
import sys

NAME = "rag_research_agent"
ASSEMBLER = "rag"   # the only module allowed to wire other modules together
# Known cross-module imports that predate M0. The set must match reality exactly, so it can only shrink.
KNOWN_DEBT = {
    ("ingest", "guard"),     # ingest/chunking.py uses guard.masking directly (should receive a Masker)
    ("store", "retrieve"),   # store/memvid_store.py uses retrieve.keyword.lex_terms (move into core or inject)
}
OPTIONAL = ("memvid_sdk", "sentence_transformers", "langchain", "langchain_core", "langgraph", "langsmith")
PURE = ("core", "edge", "diet", "knobs", "compose")


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _package(path: Path) -> str:
    return path.relative_to(PKG).parts[0]


def _module_names():
    return sorted({p.name for p in PKG.iterdir() if p.is_dir() and not p.name.startswith("_")})


def test_modules_do_not_import_each_other_except_through_core():
    edges = set()
    for path in modules():
        src = _package(path)
        if src in ("core", ASSEMBLER, "lab"):
            continue
        for name in _imports(path):
            parts = name.split(".")
            if parts[0] == NAME and len(parts) > 1 and parts[1] not in (src, "core"):
                edges.add((src, parts[1]))
    assert edges == KNOWN_DEBT, f"new cross-module imports: {edges - KNOWN_DEBT}; paid-off debt to remove: {KNOWN_DEBT - edges}"


def test_langchain_only_in_rag_or_ontology_adapter_files():
    offenders = []
    for path in modules():
        allowed = _package(path) == ASSEMBLER or (_package(path) == "ontology" and "adapter" in path.name)
        for name in _imports(path):
            if name.split(".")[0] in ("langchain", "langchain_core", "langgraph") and not allowed:
                offenders.append(str(path.relative_to(PKG)))
    assert not offenders


def _run(code: str) -> subprocess.CompletedProcess:
    root = PKG.parents[1]
    prelude = f"import sys; sys.path.insert(0, {str(root / 'src')!r})\n"
    return subprocess.run([sys.executable, "-I", "-c", prelude + code], capture_output=True, text=True, cwd=root)


BLOCKER = '''
import importlib.abc, sys
BLOCKED = {blocked!r}
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in BLOCKED or name in BLOCKED:
            raise ImportError("blocked: " + name)
sys.meta_path.insert(0, Block())
'''


def _all_files(package: str):
    return sorted(p for p in (PKG / package).rglob("*.py") if p.name != "__init__.py")


def _dotted(path: Path) -> str:
    return NAME + "." + ".".join(path.relative_to(PKG).with_suffix("").parts)


def test_pure_modules_import_without_optional_dependencies():
    targets = [_dotted(p) for pkg in PURE for p in _all_files(pkg)] + [NAME + "." + pkg for pkg in PURE]
    code = BLOCKER.format(blocked=set(OPTIONAL)) + "\n".join(f"import {t}" for t in targets)
    result = _run(code)
    assert result.returncode == 0, result.stderr[-800:]


def test_removing_any_one_module_leaves_the_others_importable():
    for removed in _module_names():
        if removed in ("core", ASSEMBLER, "lab", "__pycache__"):
            continue
        dependents = {src for src, dst in KNOWN_DEBT if dst == removed}
        targets = []
        for pkg in _module_names():
            if pkg in (removed, ASSEMBLER, "lab") or pkg in dependents:
                continue
            targets += [_dotted(p) for p in _all_files(pkg)]
        blocked = {f"{NAME}.{removed}"}
        code = BLOCKER.format(blocked=blocked) + "\n".join(f"import {t}" for t in targets)
        result = _run(code)
        assert result.returncode == 0, (removed, result.stderr[-600:])
