#!/usr/bin/env python3
"""verify_callmap.py — 用 stdlib ast 机械提取调用点，核对调用链地图。

地图文件 docs/runtime_call_map.md 中每条 `EDGE: 路径:行号 -> 调用` 都必须能在
代码里逐字找到；反过来，范围内与关键协作对象相关、但地图没收录的调用点也会
被反查出来。地图因此是"可证伪"的：代码改动导致行号漂移时，check 会立刻报错。

用法（仓库根目录执行，需要 Python 3.9+，仅用标准库）:

  python scripts/verify_callmap.py check docs/runtime_call_map.md
      核对地图：每条 EDGE 必须存在，否则报 BROKEN（行号过期或写错）。

  python scripts/verify_callmap.py missing docs/runtime_call_map.md [路径...]
      完整性反查：打印范围内调用了关键协作对象（见 WATCH）但地图未收录的
      调用点。省略路径时使用 CHECK_SCOPE。

  python scripts/verify_callmap.py extract [路径...]
      调试：打印范围内全部调用边。

目标串规范化：属性链（self.db.get_session）按点号拼接；夹在链中的表达式
（StoryOutput(...).replace_em_dashes）记作 (...).replace_em_dashes。
"""

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# check / missing 默认覆盖的"在线回合循环"代码范围。
CHECK_SCOPE = [
    "backend/app/routers/generate.py",
    "backend/app/routers/sessions.py",
    "backend/app/dependencies",
    "backend/app/services/scenario_generator",
    "backend/app/services/agents",
    "backend/app/services/game_state/manager.py",
    "backend/app/services/game_state/inference.py",
    "backend/app/services/game_state/normalization.py",
    "backend/app/services/prompt_builder/builder.py",
    "backend/app/services/prompt_builder/helpers.py",
    "backend/app/services/llm_client/client.py",
    "backend/app/services/llm_client/structured.py",
    "backend/app/services/llm_client/repair.py",
    "backend/app/services/llm_client/output_normalizer.py",
    "backend/app/services/retriever.py",
]

# missing 模式关注的协作对象：调用链里出现这些名字的调用点才参与反查。
WATCH = {
    "state_manager", "retriever", "prompt_builder", "llm_client",
    "campaign_manager", "memory_ctrl", "knowledge_service",
    "evaluation_module", "db", "knowledge", "scripted_story", "_llm",
}

EDGE_RE = re.compile(r"^EDGE:\s*(\S+):(\d+)\s*->\s*(.+?)\s*$")


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO / path


def py_files(path: Path) -> list[Path]:
    if path.is_dir():
        return [f for f in sorted(path.rglob("*.py")) if "__pycache__" not in f.parts]
    return [path]


def call_target(func: ast.AST) -> str:
    """把调用目标规范化成可 grep 的点号串。"""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = call_target(func.value)
        if not base or base.startswith("("):
            return f"(...).{func.attr}"
        return f"{base}.{func.attr}"
    return f"(...).{getattr(func, 'attr', 'call')}"


def extract(paths: list[Path]) -> set[tuple[str, int, str]]:
    edges: set[tuple[str, int, str]] = set()
    for path in paths:
        for py in py_files(path):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"WARN: 无法解析 {py}: {exc}", file=sys.stderr)
                continue
            rel = py.relative_to(REPO).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    edges.add((rel, node.lineno, call_target(node.func)))
    return edges


def map_edges(md: Path) -> set[tuple[str, int, str]]:
    edges: set[tuple[str, int, str]] = set()
    for line in md.read_text(encoding="utf-8").splitlines():
        m = EDGE_RE.match(line)
        if m:
            edges.add((m.group(1), int(m.group(2)), m.group(3)))
    return edges


def cmd_check(md: Path, paths: list[Path]) -> int:
    claimed = map_edges(md)
    actual = extract(paths)
    broken = sorted(claimed - actual)
    for path, line, target in broken:
        print(f"BROKEN: {path}:{line} -> {target}")
    print(f"\n地图共 {len(claimed)} 条边，其中 {len(broken)} 条与代码不符。"
          f"核对范围 {len(actual)} 个调用点。")
    return 1 if broken else 0


def cmd_missing(md: Path, paths: list[Path]) -> int:
    claimed = map_edges(md)
    leftover = sorted(
        (path, line, target)
        for path, line, target in extract(paths)
        if any(part in WATCH for part in target.split(".")) and (path, line, target) not in claimed
    )
    for path, line, target in leftover:
        print(f"MISSING: {path}:{line} -> {target}")
    print(f"\n{len(leftover)} 个未收录的协作对象调用点。")
    return 0


def cmd_extract(paths: list[Path]) -> int:
    for path, line, target in sorted(extract(paths)):
        print(f"EDGE: {path}:{line} -> {target}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cmd, *rest = argv
    if cmd == "check":
        return cmd_check(resolve(rest[0]), [resolve(p) for p in CHECK_SCOPE])
    if cmd == "missing":
        md = resolve(rest[0])
        paths = [resolve(p) for p in rest[1:]] or [resolve(p) for p in CHECK_SCOPE]
        return cmd_missing(md, paths)
    if cmd == "extract":
        return cmd_extract([resolve(p) for p in rest] or [resolve(p) for p in CHECK_SCOPE])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
