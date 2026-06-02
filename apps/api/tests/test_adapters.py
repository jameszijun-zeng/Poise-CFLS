"""Adapter 层单测：
- 注册表完整性
- CsvDirectoryAdapter 能读 demo_company
- merge_canonical 自然键 upsert 正确
- _safe_kwargs 脱敏

不依赖 DB / LLM；纯函数验证。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from poise.data_integration.adapters import (
    ADAPTER_REGISTRY,
    CanonicalDataset,
    CsvDirectoryAdapter,
    ExampleERPStub,
    ExcelWorkbookAdapter,
    SourceAdapter,
    get_adapter,
    merge_canonical,
    register,
)
from poise.data_integration.importers import _safe_kwargs


SEED_DIR = Path(__file__).resolve().parent.parent / "seeds" / "demo_company"


# ----- 注册表 -----


def test_builtin_adapters_registered():
    expected = {"csv_directory", "excel_workbook"}
    assert expected.issubset(set(ADAPTER_REGISTRY.keys()))


def test_get_adapter_returns_instance():
    a = get_adapter("csv_directory")
    assert isinstance(a, CsvDirectoryAdapter)
    assert isinstance(a, SourceAdapter)


def test_get_unknown_adapter_raises():
    with pytest.raises(KeyError):
        get_adapter("nonexistent_xyz")


def test_register_third_party_adapter():
    class FakeAdapter(SourceAdapter):
        name = "fake_test_adapter"

        def fetch(self, **kw):
            return CanonicalDataset()

    register(FakeAdapter)
    try:
        assert "fake_test_adapter" in ADAPTER_REGISTRY
        a = get_adapter("fake_test_adapter")
        assert isinstance(a, FakeAdapter)
    finally:
        ADAPTER_REGISTRY.pop("fake_test_adapter", None)


# ----- CanonicalDataset -----


def test_canonical_dataset_summary_and_totals():
    ds = CanonicalDataset(
        entities=[{"code": "X"}],
        cashflows=[{}, {}, {}],
    )
    assert ds.total_rows() == 4
    s = ds.summary()
    assert s["entities"] == 1
    assert s["cashflows"] == 3
    assert s["accounts"] == 0


# ----- CsvDirectoryAdapter -----


def test_csv_directory_adapter_loads_demo():
    if not SEED_DIR.exists():
        pytest.skip(f"seed dir 不存在：{SEED_DIR}")
    ds = CsvDirectoryAdapter().fetch(path=SEED_DIR)
    assert len(ds.entities) >= 1
    assert len(ds.accounts) >= 3
    assert len(ds.cashflows) >= 30
    assert len(ds.instruments) >= 10
    # 字段映射检查（应保留 CSV header 原样）
    assert "code" in ds.entities[0]
    assert "direction" in ds.cashflows[0]
    assert "expected_date" in ds.cashflows[0]


def test_csv_directory_adapter_nonexistent_path():
    with pytest.raises(FileNotFoundError):
        CsvDirectoryAdapter().fetch(path="/tmp/__nonexistent_seed_dir__")


# ----- ExampleERPStub -----


def test_example_erp_stub_not_implemented():
    """模板类必须抛 NotImplementedError 避免被误用。"""
    a = ExampleERPStub(connection_str="dummy", company_code="X")
    with pytest.raises(NotImplementedError):
        a.fetch()


# ----- merge_canonical -----


def test_merge_canonical_upserts_by_natural_key():
    base = CanonicalDataset(
        entities=[{"code": "DEMO", "name": "原名"}],
        accounts=[
            {"entity_code": "DEMO", "code": "ACC-1", "name": "旧账户"},
            {"entity_code": "DEMO", "code": "ACC-2", "name": "保持不变"},
        ],
        instruments=[{"entity_code": "DEMO", "code": "MMF-A", "rate_annual_pct": "2.0"}],
    )
    incoming = CanonicalDataset(
        entities=[{"code": "DEMO", "name": "新名"}],          # 替换
        accounts=[
            {"entity_code": "DEMO", "code": "ACC-1", "name": "新账户"},   # 替换
            {"entity_code": "DEMO", "code": "ACC-3", "name": "新增"},      # 新增
        ],
        instruments=[{"entity_code": "DEMO", "code": "MMF-A", "rate_annual_pct": "2.5"}],  # 替换
    )
    merged = merge_canonical(base, incoming)

    # entities: 1 项被替换
    assert len(merged.entities) == 1
    assert merged.entities[0]["name"] == "新名"

    # accounts: ACC-1 替换 + ACC-3 新增 = 3 条
    assert len(merged.accounts) == 3
    by_code = {a["code"]: a for a in merged.accounts}
    assert by_code["ACC-1"]["name"] == "新账户"
    assert by_code["ACC-2"]["name"] == "保持不变"
    assert by_code["ACC-3"]["name"] == "新增"

    # instruments: 利率被替换
    assert len(merged.instruments) == 1
    assert merged.instruments[0]["rate_annual_pct"] == "2.5"


def test_merge_canonical_does_not_mutate_inputs():
    base = CanonicalDataset(entities=[{"code": "A"}])
    incoming = CanonicalDataset(entities=[{"code": "B"}])
    merge_canonical(base, incoming)
    # 原 base 仍只有 A
    assert len(base.entities) == 1
    assert base.entities[0]["code"] == "A"


def test_merge_canonical_cashflows_composite_key():
    """cashflow 用复合键，金额不同视为不同行。"""
    base = CanonicalDataset(cashflows=[
        {"entity_code": "DEMO", "expected_date": "2026-06-01",
         "direction": "inflow", "category": "sales_collection",
         "counterparty": "客户A", "amount": "100"},
    ])
    incoming = CanonicalDataset(cashflows=[
        {"entity_code": "DEMO", "expected_date": "2026-06-01",
         "direction": "inflow", "category": "sales_collection",
         "counterparty": "客户A", "amount": "200"},  # 不同金额 → 新增
    ])
    merged = merge_canonical(base, incoming)
    assert len(merged.cashflows) == 2


# ----- _safe_kwargs 脱敏 -----


def test_safe_kwargs_masks_secrets():
    raw = {
        "path": "/data/x.xlsx",
        "company_code": "CN01",
        "password": "supersecret",
        "api_key": "sk-abc",
        "auth_token": "bearer-xyz",
        "connection_string": "host=db.x.com pwd=p",
        "from_date": "2026-06-01",
    }
    safe = _safe_kwargs(raw)
    # 敏感字段被替换为 ***
    assert safe["password"] == "***"
    assert safe["api_key"] == "***"
    assert safe["auth_token"] == "***"
    assert safe["connection_string"] == "***"
    # 普通字段保留
    assert safe["path"] == "/data/x.xlsx"
    assert safe["company_code"] == "CN01"
    assert safe["from_date"] == "2026-06-01"


# ----- ExcelWorkbookAdapter（依赖 openpyxl）-----


def test_excel_adapter_requires_openpyxl_or_works():
    """如果安装了 openpyxl 就跑一个 minimal 测试；否则跳过。"""
    try:
        from openpyxl import Workbook
    except ImportError:
        pytest.skip("openpyxl 未装，跳过 Excel adapter 测试")

    import tempfile

    wb = Workbook()
    ws = wb.active
    ws.title = "entities"
    ws.append(["code", "name", "base_currency"])
    ws.append(["TEST", "测试主体", "CNY"])

    ws2 = wb.create_sheet("cashflows")
    ws2.append(["entity_code", "direction", "category", "source_type",
                "expected_date", "amount", "certainty_layer"])
    ws2.append(["TEST", "inflow", "sales_collection", "ar",
                "2026-06-01", "1000000", "deterministic"])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        wb.save(f.name)
        path = f.name

    try:
        ds = ExcelWorkbookAdapter().fetch(path=path)
        assert len(ds.entities) == 1
        assert ds.entities[0]["code"] == "TEST"
        assert len(ds.cashflows) == 1
        assert ds.cashflows[0]["direction"] == "inflow"
        # 空 sheet 应返回空列表
        assert ds.accounts == []
    finally:
        import os
        os.unlink(path)
