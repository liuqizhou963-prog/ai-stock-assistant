from __future__ import annotations

import ast
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
source_path = ROOT / "skills" / "a-stock-data" / "SKILL.md"
target_path = ROOT / "apps" / "backend" / "app" / "tools" / "a_stock_data_source.py"


def python_blocks() -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in source_path.read_text(encoding="utf-8").splitlines():
        if line == "```python":
            current = []
        elif line == "```" and current is not None:
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    # Blocks 48-50 are runnable demonstrations. Block 51 contains the three
    # documented fallback functions and is therefore part of the runtime.
    return [*blocks[:47], blocks[50]]


def keep_node(node: ast.AST) -> bool:
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return True
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names: set[str] = set()
        pending = list(targets)
        while pending:
            target = pending.pop()
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                pending.extend(target.elts)
        # Keep module constants and private helpers only. Lowercase top-level
        # assignments in the Skill blocks are demonstration calls/results.
        if names and not all(name.startswith("_") or name.isupper() for name in names):
            return False
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            return bool(names & {"EM_SESSION", "_em_adapter", "_ctx", "_TICKER_RE"})
        return True
    return False


def build_module() -> str:
    nodes: list[ast.AST] = []
    for block in python_blocks():
        try:
            tree = ast.parse(textwrap.dedent(block))
        except SyntaxError as error:
            raise RuntimeError(f"Skill code block cannot be parsed: {error}") from error
        nodes.extend(node for node in tree.body if keep_node(node))
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    return "# Generated from skills/a-stock-data/SKILL.md; do not edit by hand.\n" + ast.unparse(module) + "\n"


target_path.parent.mkdir(parents=True, exist_ok=True)
target_path.write_text(build_module(), encoding="utf-8")
