"""LLM 工具（function calling）—— 6 个 tool 的 schema 与执行。

设计：
- schema 严格描述参数，避免 LLM 自由发挥
- 执行函数全部以 (db, current_user, args) 为签名，返回 JSON-friendly dict
- 任何金额/数字必须可追溯到这些 tool 的真实返回
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.rbac import CurrentUser
from poise.domain.models import (
    BalanceSnapshot,
    CashFlowItem,
    CreditLine,
    Entity,
    Forecast,
    Instrument,
    PlanAction,
    ReserveRule,
    StrategyPlan,
)
from poise.forecasting.service import latest_forecast, run_forecast
from poise.optimization.model import build_model
from poise.optimization.service import build_and_solve as svc_build_and_solve
from poise.optimization.solver import solve

# ----- Schemas -----

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_forecast",
            "description": "触发一次 13 周分层 + 双情景预测，落库后返回最新 forecast 摘要。"
                           "在用户问'未来怎样''数据更新了重算一下'或不存在最新预测时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "horizon_weeks": {
                        "type": "integer",
                        "description": "预测周数，默认 13",
                        "default": 13,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_and_solve",
            "description": "基于最新预测求解三档方案（稳健/折中/进取），落 StrategyPlan 表。"
                           "用户问'怎么配''哪个方案最好''要不要借钱'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "locks": {
                        "type": "object",
                        "description": "周次→锁定金额的映射，例如 {3: 80000000}，表示 W3 锁定 ¥80M 不可动。",
                        "additionalProperties": {"type": "number"},
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_plan",
            "description": "取出某 plan 的关键指标、首批动作和影子价（敏感性），返回结构化摘要供你叙事。"
                           "不要把 JSON 原样复述，用业务语言讲清'为什么'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "StrategyPlan 的完整 id（UUID）"},
                },
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_infeasible",
            "description": "当某档方案不可行（或用户怀疑会有缺口）时，跑松弛诊断求解，"
                           "返回每周缺口规模 slack[t]，帮你定位'缺多少、缺在哪'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_knob": {
                        "type": "string",
                        "enum": ["conservative", "balanced", "aggressive"],
                        "default": "balanced",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_overrides",
            "description": "解析自然语言假设（如'A 客户回款延后 2 周'），落到 CashFlowItem 的临时修改。"
                           "**只改输入，不绕过任何约束**。完成后用户可重新跑 run_forecast / build_and_solve。",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "用户的原始自然语言假设",
                    },
                    "operations": {
                        "type": "array",
                        "description": "由你解析出的具体操作列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {
                                    "type": "string",
                                    "enum": ["shift_week", "scale_amount", "skip"],
                                    "description": "shift_week=改周次, scale_amount=按比例调金额, skip=暂不实现",
                                },
                                "filter_counterparty": {"type": "string"},
                                "filter_category": {"type": "string"},
                                "filter_week_t": {"type": "integer"},
                                "delta_weeks": {"type": "integer"},
                                "scale": {"type": "number"},
                            },
                            "required": ["op"],
                        },
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_position",
            "description": "查询当前主体的头寸快照：期初余额、最新预测的每周净 CF、安全垫、风险标签。"
                           "便于回答'下个月怎么样''那一周缺多少'之类的现状问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "week_t": {
                        "type": "integer",
                        "description": "若指定单周，则只返回该周细节；缺省返回全部 13 周概览。",
                        "minimum": 1,
                        "maximum": 13,
                    },
                },
            },
        },
    },
]


# ----- 工具执行 -----


def _entity_id(db: Session) -> str:
    ents = list(db.scalars(select(Entity)))
    if len(ents) != 1:
        raise ValueError("当前主体数 ≠ 1，无法自动选择")
    return ents[0].id


def _to_jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _to_jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_to_jsonable(x) for x in v]
    return v


# --- 1. run_forecast ---


def tool_run_forecast(db: Session, user: CurrentUser, args: dict) -> dict:
    horizon = int(args.get("horizon_weeks", 13))
    eid = _entity_id(db)
    fc = run_forecast(db, eid, horizon=horizon)
    p = fc.payload or {}
    return {
        "forecast_id": fc.id,
        "as_of_date": fc.as_of_date.isoformat(),
        "horizon_weeks": fc.horizon_weeks,
        "initial_balance": p.get("initial_balance"),
        "gap_warning_weeks": p.get("gap_warning_weeks", []),
        "near_breach_weeks": p.get("near_breach_weeks", []),
        "neutral_net_cf_total": str(sum(Decimal(v) for v in p.get("scenarios", {}).get("neutral", {}).get("net_cf", []))),
    }


# --- 2. build_and_solve ---


def tool_build_and_solve(db: Session, user: CurrentUser, args: dict) -> dict:
    eid = _entity_id(db)
    fc = latest_forecast(db, eid)
    if not fc:
        fc = run_forecast(db, eid)
    raw_locks = args.get("locks") or {}
    locks = {int(k): Decimal(str(v)) for k, v in raw_locks.items()}

    result, plans = svc_build_and_solve(
        db, fc.id, locks=locks or None,
        actor_user_id=user.user_id, actor_role=user.role.value,
    )

    summaries = [
        {
            "plan_id": p.id,
            "risk_knob": p.risk_knob,
            "expected_net_income": str(p.expected_net_income) if p.expected_net_income else None,
            "gap_warning": p.gap_warning,
            "high_finance_dep": p.high_finance_dep,
            "n_actions": len(p.actions) if hasattr(p, "actions") else None,
            "summary": p.summary,
        }
        for p in plans
    ]
    return {
        "forecast_id": fc.id,
        "candidates": summaries,
        "infeasibility": result.infeasibility,
    }


# --- 3. explain_plan ---


def tool_explain_plan(db: Session, user: CurrentUser, args: dict) -> dict:
    plan_id = args.get("plan_id")
    if not plan_id:
        raise ValueError("plan_id 必填")
    plan = db.get(StrategyPlan, plan_id)
    if not plan:
        return {"error": f"plan {plan_id} 不存在"}
    actions = list(
        db.scalars(
            select(PlanAction).where(PlanAction.plan_id == plan.id).order_by(PlanAction.week_t, PlanAction.id)
        )
    )
    # 抽取前 6 个动作摘要，避免长度爆炸
    head = [
        {
            "week_t": a.week_t,
            "action": a.action,
            "amount": str(a.amount),
            "tenor_weeks": a.tenor_weeks,
            "instrument_note": a.notes,
        }
        for a in actions[:6]
    ]
    return {
        "plan_id": plan.id,
        "risk_knob": plan.risk_knob,
        "status": plan.status,
        "expected_net_income": str(plan.expected_net_income) if plan.expected_net_income else None,
        "gap_warning": plan.gap_warning,
        "high_finance_dep": plan.high_finance_dep,
        "finance_dep_ratio": (plan.payload or {}).get("finance_dep_ratio"),
        "summary": plan.summary,
        "total_actions": len(actions),
        "head_actions": head,
        "safety_cushion_curve": plan.safety_cushion_curve,
    }


# --- 4. diagnose_infeasible ---


def tool_diagnose_infeasible(db: Session, user: CurrentUser, args: dict) -> dict:
    from poise.optimization.multi_plan import _build_inputs_from_forecast  # local

    eid = _entity_id(db)
    fc = latest_forecast(db, eid)
    if not fc:
        return {"error": "暂无预测，请先调用 run_forecast"}
    net_cf, min_cash, b0 = _build_inputs_from_forecast(fc)
    instruments = list(db.scalars(select(Instrument).where(Instrument.entity_id == eid)))
    credit_lines = list(db.scalars(select(CreditLine).where(CreditLine.entity_id == eid)))
    knob = args.get("risk_knob", "balanced")
    handles = build_model(
        forecast_net_cf=net_cf, initial_balance=b0, min_cash=min_cash,
        instruments=instruments, credit_lines=credit_lines,
        horizon=fc.horizon_weeks, risk_knob=knob, with_slack=True,
    )
    sol = solve(handles)
    if sol.status != "optimal":
        return {"status": sol.status, "note": "诊断求解未完成"}
    slack_by_week = [
        {"week_t": t + 1, "slack": str(sol.slack_curve[t])}
        for t in range(len(sol.slack_curve))
        if sol.slack_curve[t] > 1
    ]
    total = sum(float(s) for s in sol.slack_curve)
    return {
        "risk_knob": knob,
        "total_slack": str(total),
        "gap_weeks": slack_by_week,
        "note": "slack 为正即表示该周缺口规模。若 gap_weeks 非空，需提高授信、推迟支出或加大融资。",
    }


# --- 5. apply_overrides ---


def tool_apply_overrides(db: Session, user: CurrentUser, args: dict) -> dict:
    """把"A 客户回款延后 N 周""W3 支出打 8 折"等转为 CashFlowItem 修改。

    Phase 4 MVP 只支持两类操作：shift_week / scale_amount。
    实际写入 DB 是有"风险"的——所以这里返回 dry_run 预览，让用户确认后再实施。
    """
    description = args.get("description", "")
    ops = args.get("operations", []) or []
    eid = _entity_id(db)
    cf_items = list(db.scalars(select(CashFlowItem).where(CashFlowItem.entity_id == eid)))

    preview: list[dict] = []
    for op in ops:
        op_kind = op.get("op")
        cp_filter = (op.get("filter_counterparty") or "").strip()
        cat_filter = (op.get("filter_category") or "").strip()
        week_filter = op.get("filter_week_t")
        matched = [
            it for it in cf_items
            if (not cp_filter or (it.counterparty and cp_filter in it.counterparty))
            and (not cat_filter or it.category == cat_filter)
            and (week_filter is None or it.week_t == week_filter)
        ]
        op_preview = {
            "op": op_kind,
            "filters": {"counterparty": cp_filter, "category": cat_filter, "week_t": week_filter},
            "matched_count": len(matched),
            "matched_items": [
                {
                    "id": it.id, "week_t": it.week_t, "amount": str(it.amount),
                    "category": it.category, "counterparty": it.counterparty,
                }
                for it in matched[:5]
            ],
        }
        if op_kind == "shift_week":
            op_preview["delta_weeks"] = op.get("delta_weeks")
        elif op_kind == "scale_amount":
            op_preview["scale"] = op.get("scale")
        preview.append(op_preview)

    return {
        "description": description,
        "dry_run": True,
        "preview": preview,
        "note": "本次仅返回预览，未真正修改数据。Phase 4 MVP 默认不写库，"
                "由用户在 UI 确认后再触发写入（Phase 5 will 接入 commit 入口）。",
    }


# --- 6. query_position ---


def tool_query_position(db: Session, user: CurrentUser, args: dict) -> dict:
    eid = _entity_id(db)
    fc = latest_forecast(db, eid)
    bal = sum(
        (b.available_balance for b in db.scalars(
            select(BalanceSnapshot).where(BalanceSnapshot.entity_id == eid)
        )),
        Decimal(0),
    )
    rule = db.scalar(select(ReserveRule).where(ReserveRule.entity_id == eid))
    out: dict[str, Any] = {
        "entity_id": eid,
        "total_balance": str(bal),
        "reserve_rule": (
            {
                "type": rule.rule_type,
                "fixed_value": str(rule.fixed_value) if rule.fixed_value else None,
                "rolling_weeks": rule.rolling_weeks,
            }
            if rule else None
        ),
    }
    if fc:
        p = fc.payload or {}
        out["forecast_id"] = fc.id
        out["as_of_date"] = fc.as_of_date.isoformat()
        out["gap_warning_weeks"] = p.get("gap_warning_weeks", [])
        out["near_breach_weeks"] = p.get("near_breach_weeks", [])
        wk = args.get("week_t")
        if wk:
            i = int(wk) - 1
            scn = p.get("scenarios", {})
            out["week_detail"] = {
                "week_t": int(wk),
                "date": (p.get("week_dates") or [None] * 13)[i],
                "min_cash": (p.get("min_cash") or [None] * 13)[i],
                "neutral": {
                    "net_cf": scn.get("neutral", {}).get("net_cf", [None] * 13)[i],
                    "balance": scn.get("neutral", {}).get("balance", [None] * 13)[i],
                    "safety_cushion": scn.get("neutral", {}).get("safety_cushion", [None] * 13)[i],
                },
                "pessimistic": {
                    "net_cf": scn.get("pessimistic", {}).get("net_cf", [None] * 13)[i],
                    "balance": scn.get("pessimistic", {}).get("balance", [None] * 13)[i],
                    "safety_cushion": scn.get("pessimistic", {}).get("safety_cushion", [None] * 13)[i],
                },
            }
    return out


# ----- 调度表 -----


TOOL_REGISTRY: dict[str, Callable[[Session, CurrentUser, dict], dict]] = {
    "run_forecast": tool_run_forecast,
    "build_and_solve": tool_build_and_solve,
    "explain_plan": tool_explain_plan,
    "diagnose_infeasible": tool_diagnose_infeasible,
    "apply_overrides": tool_apply_overrides,
    "query_position": tool_query_position,
}


def dispatch_tool(name: str, db: Session, user: CurrentUser, args_json: str) -> dict:
    """统一入口：解析参数、执行、捕获异常、返回 JSON-friendly dict。"""
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return {"error": f"未知 tool: {name}"}
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        return {"error": f"参数 JSON 解析失败: {e}"}
    try:
        return _to_jsonable(fn(db, user, args))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
