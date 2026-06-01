"""引导脚本：创建默认 Entity + 四个测试角色用户。

用法（容器内）:
    python -m poise.scripts.bootstrap

仅在 Phase 0 / 本地开发使用，生产部署需替换为管理员手动创建流程。
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from poise.core.database import SessionLocal
from poise.core.rbac import Role
from poise.core.security import hash_password
from poise.domain.models import Entity, User

DEFAULT_PASSWORD = "Poise@2026"

DEFAULT_USERS: list[tuple[str, str, Role]] = [
    ("admin", "管理员", Role.admin),
    ("treasurer", "资金主管", Role.treasurer),
    ("analyst", "出纳分析师", Role.analyst),
    ("viewer", "只读用户", Role.viewer),
]


def main() -> int:
    with SessionLocal() as db:
        entity = db.scalar(select(Entity).where(Entity.code == "DEMO"))
        if not entity:
            entity = Entity(name="稳盈示范企业", code="DEMO", base_currency="CNY")
            db.add(entity)
            db.flush()
            print(f"[+] created entity: {entity.id} (DEMO)")
        else:
            print(f"[=] entity exists: {entity.id} (DEMO)")

        for username, display, role in DEFAULT_USERS:
            existing = db.scalar(select(User).where(User.username == username))
            if existing:
                print(f"[=] user exists: {username} ({role.value})")
                continue
            db.add(
                User(
                    entity_id=entity.id,
                    username=username,
                    display_name=display,
                    password_hash=hash_password(DEFAULT_PASSWORD),
                    role=role.value,
                )
            )
            print(f"[+] created user: {username} / {DEFAULT_PASSWORD} ({role.value})")

        db.commit()

    print()
    print(f"默认密码: {DEFAULT_PASSWORD}")
    print("登录: POST /api/v1/auth/login (form: username, password)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
