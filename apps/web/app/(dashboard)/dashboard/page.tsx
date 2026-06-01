import { getServerSession } from "next-auth";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { KpiCard } from "@/components/kpi-card";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

import { ForecastMiniChart } from "./forecast-mini-chart";
import { QuickActions } from "./quick-actions";

// ===== 类型 =====
type Account = {
  id: string;
  code: string;
  name: string;
  bank_name: string | null;
  account_type: string;
  currency: string;
  is_active: boolean;
};
type Balance = {
  id: number;
  account_id: string;
  as_of_date: string;
  balance: string;
  available_balance: string;
  restricted_balance: string;
  currency: string;
};
type ForecastPayload = {
  anchor: string;
  week_dates: string[];
  initial_balance: string;
  min_cash: string[];
  scenarios: {
    neutral: { balance: string[]; net_cf: string[] };
    pessimistic: { balance: string[]; safety_cushion: string[] };
  };
  gap_warning_weeks: number[];
  near_breach_weeks: number[];
};
type Forecast = {
  id: string;
  as_of_date: string;
  horizon_weeks: number;
  created_at: string;
  payload: ForecastPayload;
};
type Plan = {
  id: string;
  risk_knob: "conservative" | "balanced" | "aggressive";
  status: "draft" | "proposed" | "adopted" | "rejected";
  expected_net_income: string | null;
  gap_warning: boolean;
  high_finance_dep: boolean;
  payload: { finance_dep_ratio?: number } | null;
};
type Health = { status: string; version: string; db: string };
type RollingRun = { id: string; triggered_at: string; summary: string | null };

const ACCT_TYPE_LABEL: Record<string, string> = {
  basic: "基本户",
  general: "一般户",
  special: "专户",
};

const KNOB_LABEL: Record<string, string> = {
  conservative: "稳健",
  balanced: "折中",
  aggressive: "进取",
};

const fmtCNY = (v: string | number) => {
  const n = Number(v);
  if (Math.abs(n) >= 1e8) return `¥${(n / 1e8).toFixed(2)} 亿`;
  if (Math.abs(n) >= 1e4) return `¥${(n / 1e4).toFixed(1)} 万`;
  return `¥${n.toLocaleString("zh-CN")}`;
};

export default async function DashboardPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error -- extended session
  const token: string | undefined = session?.accessToken;
  const userName = session?.user?.name ?? "用户";
  // @ts-expect-error
  const role: string = session?.user?.role ?? "viewer";

  // 并行拉取所有数据
  const [health, accounts, balances, forecast, rolling]: [
    Health | null,
    Account[],
    Balance[],
    Forecast | null,
    RollingRun[],
  ] = await Promise.all([
    apiFetch<Health>("/api/v1/health", { token }).catch(() => null),
    apiFetch<Account[]>("/api/v1/data/accounts", { token }).catch(() => []),
    apiFetch<Balance[]>("/api/v1/data/balances", { token }).catch(() => []),
    apiFetch<Forecast | null>("/api/v1/forecast/latest", { token }).catch(() => null),
    apiFetch<RollingRun[]>("/api/v1/feedback/rolling-runs?limit=1", { token }).catch(() => []),
  ]);

  let plans: Plan[] = [];
  if (forecast) {
    plans = await apiFetch<Plan[]>(`/api/v1/plans/by-forecast/${forecast.id}`, { token }).catch(
      () => [],
    );
  }

  // === 派生指标 ===
  const latestBalanceByAcct = new Map<string, Balance>();
  for (const b of balances) {
    const prev = latestBalanceByAcct.get(b.account_id);
    if (!prev || prev.as_of_date < b.as_of_date) latestBalanceByAcct.set(b.account_id, b);
  }
  const totalAvailable = [...latestBalanceByAcct.values()].reduce(
    (s, b) => s + Number(b.available_balance),
    0,
  );

  const horizon = forecast?.payload.week_dates?.length ?? 0;
  const neutralEnd = horizon
    ? Number(forecast!.payload.scenarios.neutral.balance[horizon - 1])
    : null;
  const pessEnd = horizon
    ? Number(forecast!.payload.scenarios.pessimistic.balance[horizon - 1])
    : null;
  const initBal = forecast ? Number(forecast.payload.initial_balance) : totalAvailable;
  const netChange = neutralEnd != null ? neutralEnd - initBal : null;
  const gapWeeks = forecast?.payload.gap_warning_weeks ?? [];
  const nearWeeks = forecast?.payload.near_breach_weeks ?? [];
  const totalAlerts = gapWeeks.length + nearWeeks.length;

  const adopted = plans.find((p) => p.status === "adopted");
  const balanced = plans.find((p) => p.risk_knob === "balanced");
  const recommended = adopted ?? balanced ?? plans[0];

  const maxBalance = Math.max(
    1,
    ...[...latestBalanceByAcct.values()].map((b) => Number(b.available_balance)),
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">稳盈 · 资金驾驶舱</h1>
          <p className="text-sm text-muted-foreground">
            欢迎，{userName}（{role}） · 实时头寸 · 13 周展望 · 决策建议
          </p>
        </div>
        <QuickActions />
      </header>

      {/* KPI Row */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard
          label="总可用头寸"
          value={fmtCNY(totalAvailable)}
          hint={`${latestBalanceByAcct.size} 个账户合计`}
          tone="primary"
        />
        <KpiCard
          label="13 周期末余额（中性）"
          value={neutralEnd != null ? fmtCNY(neutralEnd) : "—"}
          hint={
            netChange != null
              ? `相比期初 ${netChange >= 0 ? "+" : ""}${fmtCNY(netChange)}`
              : forecast
                ? "—"
                : "尚无预测"
          }
          tone="success"
          trend={netChange != null ? (netChange >= 0 ? "up" : "down") : null}
        />
        <KpiCard
          label="13 周期末余额（悲观）"
          value={pessEnd != null ? fmtCNY(pessEnd) : "—"}
          hint="悲观情景下的压力测试结果"
          tone={
            pessEnd != null && totalAvailable > 0
              ? pessEnd / totalAvailable < 0.2
                ? "destructive"
                : pessEnd / totalAvailable < 0.5
                  ? "warning"
                  : "muted"
              : "muted"
          }
        />
        <KpiCard
          label="风险预警"
          value={totalAlerts}
          unit={totalAlerts > 0 ? "周" : ""}
          hint={
            totalAlerts > 0
              ? `${gapWeeks.length} 缺口 · ${nearWeeks.length} 擦边`
              : "未来 13 周无风险标签"
          }
          tone={gapWeeks.length > 0 ? "destructive" : nearWeeks.length > 0 ? "warning" : "success"}
          badge={
            gapWeeks.length > 0
              ? { text: "缺口", variant: "destructive" }
              : nearWeeks.length > 0
                ? { text: "擦边", variant: "warning" }
                : { text: "健康", variant: "success" }
          }
        />
      </div>

      {/* 中部：账户分布 + 13 周曲线 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>账户余额分布</CardTitle>
            <CardDescription>{accounts.length} 个银行账户</CardDescription>
          </CardHeader>
          <CardContent>
            {accounts.length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">尚未导入账户数据。</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {accounts.map((a) => {
                  const b = latestBalanceByAcct.get(a.id);
                  const avail = b ? Number(b.available_balance) : 0;
                  const restricted = b ? Number(b.restricted_balance) : 0;
                  const pct = (avail / maxBalance) * 100;
                  return (
                    <li key={a.id} className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex min-w-0 items-center gap-2">
                          <Badge variant="default">
                            {ACCT_TYPE_LABEL[a.account_type] ?? a.account_type}
                          </Badge>
                          <span className="truncate font-medium">{a.name}</span>
                        </div>
                        <span className="ml-2 tabular-nums font-semibold text-primary">
                          {fmtCNY(avail)}
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-primary transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{a.bank_name ?? "—"}</span>
                        {restricted > 0 && <span>受限 {fmtCNY(restricted)}</span>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs">
              <span className="text-muted-foreground">合计可用</span>
              <span className="text-base font-semibold tabular-nums text-primary">
                {fmtCNY(totalAvailable)}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>13 周余额演化</CardTitle>
                <CardDescription>
                  {forecast
                    ? `预测 ${forecast.id.slice(0, 8)}... · ${new Date(forecast.created_at).toLocaleString("zh-CN")}`
                    : "暂无预测"}
                </CardDescription>
              </div>
              <Link href="/forecast" className="text-xs text-primary hover:underline">
                详情 →
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {forecast ? (
              <>
                <ForecastMiniChart payload={forecast.payload} />
                <div className="mt-2 flex flex-wrap items-center justify-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-0.5 w-4 bg-primary" />
                    中性
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-0.5 w-4 bg-warning" />
                    悲观
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-0.5 w-4 bg-destructive" />
                    最低备付
                  </span>
                  {gapWeeks.length > 0 && (
                    <Badge variant="destructive">W{gapWeeks.join(", W")} 缺口</Badge>
                  )}
                  {nearWeeks.length > 0 && (
                    <Badge variant="warning">W{nearWeeks.join(", W")} 擦边</Badge>
                  )}
                </div>
              </>
            ) : (
              <div className="flex h-[200px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                尚未生成预测
                <Link href="/forecast" className="text-xs text-primary hover:underline">
                  去生成首份预测 →
                </Link>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 下部：当前方案 + 系统状态 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>当前推荐方案</CardTitle>
                <CardDescription>基于最新预测的 MILP 求解结果</CardDescription>
              </div>
              <Link href="/plans" className="text-xs text-primary hover:underline">
                三档对比 →
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {!recommended ? (
              <div className="py-6 text-sm text-muted-foreground">
                尚未求解 ·{" "}
                <Link href="/plans" className="text-primary hover:underline">
                  去求解三档方案 →
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {plans.map((p) => {
                  const isReco = p.id === recommended.id;
                  return (
                    <div
                      key={p.id}
                      className={
                        isReco
                          ? "rounded-lg border-2 border-primary bg-primary/5 p-3"
                          : "rounded-lg border p-3"
                      }
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold">
                          {KNOB_LABEL[p.risk_knob]}
                        </span>
                        {p.status === "adopted" && (
                          <Badge variant="success">已采纳</Badge>
                        )}
                        {p.status === "rejected" && (
                          <Badge variant="default">已否决</Badge>
                        )}
                        {p.status === "proposed" && isReco && (
                          <Badge variant="primary">推荐</Badge>
                        )}
                      </div>
                      <div className="mt-1.5 text-xl font-bold tabular-nums text-primary">
                        {p.expected_net_income ? fmtCNY(p.expected_net_income) : "—"}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">预期净收益</div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {p.gap_warning && <Badge variant="destructive">缺口</Badge>}
                        {p.high_finance_dep && <Badge variant="warning">高融资</Badge>}
                        {!p.gap_warning && !p.high_finance_dep && (
                          <Badge variant="success">合规</Badge>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>系统状态</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">API</span>
              <Badge variant={health?.status === "ok" ? "success" : "destructive"}>
                {health?.status ?? "—"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">数据库</span>
              <Badge variant={health?.db === "ok" ? "success" : "destructive"}>
                {health?.db ?? "—"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">版本</span>
              <span className="font-mono text-xs">v{health?.version ?? "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 border-t pt-3">
              <span className="text-xs text-muted-foreground">最近滚动重跑</span>
              {rolling[0] ? (
                <>
                  <span className="text-xs">
                    {new Date(rolling[0].triggered_at).toLocaleString("zh-CN")}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {rolling[0].summary?.slice(0, 50) ?? ""}...
                  </span>
                </>
              ) : (
                <span className="text-xs text-muted-foreground">尚未滚动</span>
              )}
              <Link href="/accuracy" className="mt-1 text-xs text-primary hover:underline">
                MAPE 看板 →
              </Link>
            </div>
            <div className="flex flex-col gap-0.5 border-t pt-3">
              <span className="text-xs text-muted-foreground">快捷链接</span>
              <Link href="/alerts" className="text-xs text-primary hover:underline">
                预警中心 →
              </Link>
              {(role === "admin" || role === "treasurer") && (
                <Link href="/admin" className="text-xs text-primary hover:underline">
                  管理后台 →
                </Link>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
