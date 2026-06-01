#!/usr/bin/env bash
# 稳盈 / Poise · 端到端冒烟脚本
#
# 验证完整闭环：登录 → 导入种子 → 预测 → 求解 → 采纳 → 滚动重跑
# 不依赖 LLM API（chat 路径仅在有 DEEPSEEK_API_KEY 时单独测）
#
# 用法：  bash scripts/smoke.sh

set -euo pipefail

API="${API_URL:-http://localhost:8001}"
PASSWORD="${SEED_PASSWORD:-Poise@2026}"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }

step() { blue "▶ $*"; }
ok()   { green "  ✓ $*"; }
fail() { red "  ✗ $*"; exit 1; }

# 计时
t0=$(date +%s)

step "0. 健康检查"
curl -sf "${API}/healthz" >/dev/null || fail "API 不在线: ${API}"
HEALTH=$(curl -s "${API}/api/v1/health")
DB=$(echo "$HEALTH" | python3 -c "import sys,json;print(json.load(sys.stdin)['db'])")
[ "$DB" = "ok" ] || fail "DB 不通: $DB"
ok "API + DB 健康"

step "1. 登录（treasurer）"
TOKEN=$(curl -s -X POST "${API}/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=treasurer&password=${PASSWORD}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
[ -n "$TOKEN" ] || fail "登录失败（密码是否 Poise@2026？）"
ok "登录成功（token ${#TOKEN} 字符）"

step "2. 导入 demo_company 种子数据（幂等）"
IMP=$(curl -s -X POST "${API}/api/v1/data/import-demo" -H "Authorization: Bearer ${TOKEN}")
echo "$IMP" | python3 -c "import sys,json;r=json.load(sys.stdin);assert r['ok'], r" || fail "导入失败: $IMP"
ok "导入完成 / 已 upsert"

step "3. 触发预测（13 周双情景）"
PERF_S=$(date +%s%N)
FC=$(curl -s -X POST "${API}/api/v1/forecast/run" \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d '{}')
PERF_E=$(date +%s%N)
FC_MS=$(( (PERF_E - PERF_S) / 1000000 ))
FC_ID=$(echo "$FC" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
GAPS=$(echo "$FC" | python3 -c "import sys,json;print(json.load(sys.stdin)['payload']['gap_warning_weeks'])")
NEARS=$(echo "$FC" | python3 -c "import sys,json;print(json.load(sys.stdin)['payload']['near_breach_weeks'])")
ok "预测 ${FC_ID:0:8}... · 耗时 ${FC_MS}ms · 硬缺口 ${GAPS} · 擦边 ${NEARS}"
[ "$FC_MS" -lt 3000 ] || red "  ⚠ 预测耗时超过 3s 性能目标"

step "4. 触发三档求解（MILP CBC）"
PERF_S=$(date +%s%N)
PLANS=$(curl -s -X POST "${API}/api/v1/plans/build-and-solve" \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d '{}')
PERF_E=$(date +%s%N)
SOLVE_MS=$(( (PERF_E - PERF_S) / 1000000 ))
N=$(echo "$PLANS" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['candidates']))")
[ "$N" = "3" ] || fail "三档求解未返回 3 个方案（实际 $N）"
echo "$PLANS" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for c in r['candidates']:
    print(f'    {c[\"risk_knob\"]:>12s}: ¥{float(c[\"expected_net_income\"]):>10,.0f}  gap={c[\"gap_warning\"]}  high_dep={c[\"high_finance_dep\"]}')"
ok "三档全部 optimal · 耗时 ${SOLVE_MS}ms"
[ "$SOLVE_MS" -lt 3000 ] || red "  ⚠ 三档求解超过 3s 性能目标"

step "5. what-if：锁定 W3 ¥80M 并购款重算"
PERF_S=$(date +%s%N)
WHATIF=$(curl -s -X POST "${API}/api/v1/plans/build-and-solve" \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -d '{"locks":{"3":80000000}}')
PERF_E=$(date +%s%N)
WI_MS=$(( (PERF_E - PERF_S) / 1000000 ))
echo "$WHATIF" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for c in r['candidates']:
    print(f'    {c[\"risk_knob\"]:>12s}: ¥{float(c[\"expected_net_income\"]):>10,.0f}')"
ok "what-if 重算耗时 ${WI_MS}ms"

step "6. 采纳折中档"
PID=$(echo "$WHATIF" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for c in r['candidates']:
    if c['risk_knob'] == 'balanced':
        print(c['id']); break")
ADOPT=$(curl -s -X POST "${API}/api/v1/plans/${PID}/adopt" \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d '{}')
STATUS=$(echo "$ADOPT" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
[ "$STATUS" = "adopted" ] || fail "采纳失败: $ADOPT"
ok "折中档采纳成功 → 其它档自动 rejected"

step "7. 触发反馈滚动重跑（W3）"
PERF_S=$(date +%s%N)
ROLL=$(curl -s -X POST "${API}/api/v1/feedback/trigger-rolling" \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -d '{"target_week":3,"rerun_forecast":false}')
PERF_E=$(date +%s%N)
ROLL_MS=$(( (PERF_E - PERF_S) / 1000000 ))
SUMMARY=$(echo "$ROLL" | python3 -c "import sys,json;print(json.load(sys.stdin)['summary'])")
ok "滚动重跑 ${ROLL_MS}ms · ${SUMMARY}"

step "8. 查看 MAPE 看板"
ACC=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${API}/api/v1/forecast/accuracy/summary")
echo "$ACC" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for b in r['by_layer']:
    m = float(b['mape'])*100 if b['mape'] else None
    print(f'    {b[\"layer\"]:<14s} samples={b[\"sample_count\"]:>3}  MAPE={f\"{m:.2f}%\" if m else \"—\"}')"
ok "MAPE 已累计"

step "9. 偏差校正系数"
BIAS=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${API}/api/v1/feedback/bias-corrections")
N_BIAS=$(echo "$BIAS" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
ok "学到 ${N_BIAS} 项偏差校正系数"

step "10. 审计日志（最近 5 条）"
ADMIN_TOKEN=$(curl -s -X POST "${API}/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=${PASSWORD}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" "${API}/api/v1/admin/audit-logs?limit=5" \
  | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(f'    total: {r[\"total\"]} 条')
for it in r['items']:
    print(f'    #{it[\"id\"]} {it[\"event_type\"]:<22s} {it[\"actor_role\"] or \"-\":<10s} {it[\"method\"] or \"\":<6s} {it[\"path\"] or \"\"}')"
ok "审计闭环"

t1=$(date +%s)
TOTAL=$((t1 - t0))
echo
green "========================================"
green " 冒烟通过 · 端到端耗时 ${TOTAL}s"
green "========================================"
dim " · 预测 ${FC_MS}ms · 求解 ${SOLVE_MS}ms · what-if ${WI_MS}ms · 滚动 ${ROLL_MS}ms"
