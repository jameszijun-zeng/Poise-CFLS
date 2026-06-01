"""命令行工具：导入 demo_company 种子数据。

用法（容器内）：
    python -m poise.data_integration.cli import-demo
"""

from __future__ import annotations

import sys

from poise.core.database import SessionLocal
from poise.data_integration.importers import import_demo_company


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv or argv[0] not in {"import-demo"}:
        print("usage: python -m poise.data_integration.cli import-demo")
        return 2

    with SessionLocal() as db:
        summary = import_demo_company(db, actor_user_id="cli", actor_role="admin")

    print()
    print("=== Imported ===")
    for tbl, n in summary.imported.items():
        print(f"  {tbl}: +{n}")
    print()
    print("=== Skipped (upsert / failed validation) ===")
    for tbl, n in summary.skipped.items():
        print(f"  {tbl}: {n}")
    print()
    errors = [i for i in summary.issues if i.severity == "error"]
    warnings = [i for i in summary.issues if i.severity == "warning"]
    if warnings:
        print(f"=== Warnings ({len(warnings)}) ===")
        for w in warnings[:20]:
            print(f"  [{w.table}] row={w.row} field={w.field}: {w.message}")
    if errors:
        print(f"=== Errors ({len(errors)}) ===")
        for e in errors[:20]:
            print(f"  [{e.table}] row={e.row} field={e.field}: {e.message}")
    print()
    print(f"ok={summary.ok}")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
