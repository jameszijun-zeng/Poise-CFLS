#!/usr/bin/env bash
# 稳盈 / Poise · demo 录制流程总控
#
# 流程：
#   1. 重置 demo 数据（保证每次干净）
#   2. 提示启动屏幕录制
#   3. 用户按 Enter
#   4. 启动 Puppeteer 自动演示
#   5. 演完后提示停止录制
#
# 用法：bash scripts/record_demo.sh

set -e

green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
dim()   { printf '\033[2m%s\033[0m\n' "$*"; }

API="${API_URL:-http://localhost:8001}"
WEB="${WEB_BASE:-http://localhost:3000}"

echo
green "================================================"
green "  稳盈 / Poise · Demo 录制启动器"
green "================================================"
echo

# Step 1: 健康检查
blue "▶ 1/4 健康检查"
if ! curl -sf "$API/healthz" > /dev/null 2>&1; then
  red "  ✗ API 不在线：$API"
  red "  请先运行：make up"
  exit 1
fi
green "  ✓ API + Web 就绪"
echo

# Step 2: 重置 + 重导数据
blue "▶ 2/4 重置 demo 数据"
dim "  这会清空旧 forecast/plans 以便录制时所有按钮第一次点都立即生效"
dim "  （保留：用户、品种、授信、备付、现金流；清掉：forecast/plans/actuals）"
docker compose exec -T postgres psql -U poise -d poise -c "
  DELETE FROM plan_actions;
  DELETE FROM strategy_plans;
  DELETE FROM forecast_weeks;
  DELETE FROM forecasts;
  DELETE FROM actual_cash_flows;
  DELETE FROM bias_corrections;
  DELETE FROM rolling_runs;
  DELETE FROM conversation_messages WHERE conversation_id IN (
    SELECT id FROM conversations WHERE updated_at < NOW() - INTERVAL '1 minute'
  );
" > /dev/null 2>&1 || true
green "  ✓ 已重置"
echo

# Step 3: 提示录制
blue "▶ 3/4 准备屏幕录制"
echo
yellow "  请现在操作："
yellow "    1. 打开屏幕录制软件（QuickTime / OBS / ScreenFlow）"
yellow "    2. 设置区域：全屏，或 1920×1080"
yellow "    3. 开始录制"
yellow "    4. 切回 Chrome 浏览器（自动会启动）"
echo
yellow "  按 Enter 继续，将打开 Chrome 并自动演示约 5 分钟..."
read -r
echo

# Step 4: 启动 demo
blue "▶ 4/4 启动自动演示"
echo
NODE_PATH=$(npm root -g) WEB_BASE="$WEB" node scripts/demo_runner.js
echo
green "================================================"
green "  演示结束 · 请停止屏幕录制"
green "================================================"
echo
yellow "  下一步建议："
yellow "    · 用 iMovie / Final Cut / DaVinci Resolve 后期"
yellow "    · 配音参考 doc/Demo录制脚本_5分钟.md"
yellow "    · 关键数字处放大强调"
echo
