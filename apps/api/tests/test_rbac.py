import pytest
from fastapi import HTTPException

from poise.core.rbac import PERMISSIONS, CurrentUser, Role, require


def _check(perm: str, role: Role) -> None:
    user = CurrentUser(user_id="u1", role=role)
    checker = require(perm)
    checker(user)


def test_admin_has_all_permissions():
    for perm in PERMISSIONS:
        _check(perm, Role.admin)


def test_viewer_can_read_but_not_write():
    _check("data.read", Role.viewer)
    with pytest.raises(HTTPException) as exc:
        _check("data.write", Role.viewer)
    assert exc.value.status_code == 403


def test_analyst_cannot_adopt_plan():
    _check("plan.solve", Role.analyst)
    with pytest.raises(HTTPException):
        _check("plan.adopt", Role.analyst)


def test_treasurer_can_adopt_plan():
    _check("plan.adopt", Role.treasurer)


def test_unknown_permission_raises_500():
    user = CurrentUser(user_id="u1", role=Role.admin)
    checker = require("nonexistent.perm")
    with pytest.raises(HTTPException) as exc:
        checker(user)
    assert exc.value.status_code == 500
