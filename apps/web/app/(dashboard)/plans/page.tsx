import { getServerSession } from "next-auth";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DataTable, fmtMoney, fmtPct } from "@/components/data-table";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

import { AdoptButtons } from "./adopt-buttons";
import { BalanceCompareChart, CushionCompareChart } from "./cushion-chart";
import { PlansActionsBar } from "./plans-actions-bar";

type PlanAction = {
  id: number;
  week_t: number;
  instrument_id: string | null;
  action: "invest" | "draw" | "redeem" | "repay";
  amount: string;
  tenor_weeks: number | null;
  notes: string | null;
};

type Plan = {
  id: string;
  entity_id: string;
  forecast_id: string | null;
  risk_knob: "conservative" | "balanced" | "aggressive";
  status: "draft" | "proposed" | "adopted" | "rejected";
  expected_net_income: string | null;
  safety_cushion_curve: (string | number)[] | null;
  gap_warning: boolean;
  high_finance_dep: boolean;
  summary: string | null;
  payload: {
    balance_curve?: string[];
    finance_dep_ratio?: number;
    gap_warning_weeks?: number[];
    objective?: string;
    solver_status?: string;
  } | null;
  created_at: string;
  actions: PlanAction[];
};

type Forecast = { id: string; as_of_date: string; created_at: string };

const KNOB_LABEL: Record<string, string> = {
  conservative: "稳健",
  balanced: "折中",
  aggressive: "进取",
};
const KNOB_TONE: Record<string, "success" | "primary" | "warning"> = {
  conservative: "success",
  balanced: "primary",
  aggressive: "warning",
};
const ACTION_LABEL: Record<string, string> = {
  invest: "投资",
  draw: "动用授信",
  redeem: "提前赎回",
  repay: "偿还融资",
};

export default async function PlansPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  // 1. 找最新预测
  let forecast: Forecast | null = null;
  try {
    forecast = await apiFetch<Forecast | null>("/api/v1/forecast/latest", { token });
  } catch {}

  // 2. 取该预测下的三档最新方案
  let plans: Plan[] = [];
  if (forecast) {
    try {
      plans = await apiFetch<Plan[]>(`/api/v1/plans/by-forecast/${forecast.id}`, { token });
    } catch {}
  }

  if (!forecast) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold">方案对比</h1>
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            尚无预测，请先在「13 周看板」生成一份预测，再来求解方案。
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">方案对比</h1>
          <p className="text-sm text-muted-foreground">
            基于预测 {forecast.id.slice(0, 8)}... · as-of {forecast.as_of_date}
            <span className="ml-2 text-xs">
              {plans.length > 0 && plans[0].created_at &&
                `求解于 ${new Date(plans[0].created_at).toLocaleString("zh-CN")}`}
            </span>
          </p>
        </div>
        <PlansActionsBar />
      </header>

      {plans.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            预测已就绪，请点击右上角"重新求解"生成三档方案。
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            {plans.map((p) => (
              <Card key={p.id} className={p.status === "adopted" ? "ring-2 ring-success" : ""}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardDescription>
                      <Badge variant={KNOB_TONE[p.risk_knob]}>{KNOB_LABEL[p.risk_knob]}</Badge>
                    </CardDescription>
                    <span className="text-xs text-muted-foreground">{p.id.slice(0, 8)}...</span>
                  </div>
                  <CardTitle className="text-2xl">
                    {p.expected_net_income ? fmtMoney(p.expected_net_income) : "—"}
                  </CardTitle>
                  <CardDescription>预期净收益（horizon 内）</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">投资动作</span>
                    <span>
                      {p.actions.filter((a) => a.action === "invest").length} 笔 / ¥
                      {(p.actions
                        .filter((a) => a.action === "invest")
                        .reduce((s, a) => s + Number(a.amount), 0) / 1e6).toFixed(0)}
                      M
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">融资动作</span>
                    <span>
                      {p.actions.filter((a) => a.action === "draw").length} 笔 / ¥
                      {(p.actions
                        .filter((a) => a.action === "draw")
                        .reduce((s, a) => s + Number(a.amount), 0) / 1e6).toFixed(0)}
                      M
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">融资依赖度</span>
                    <span className={p.high_finance_dep ? "font-semibold text-warning" : ""}>
                      {fmtPct(p.payload?.finance_dep_ratio ?? 0)}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {p.gap_warning && <Badge variant="destructive">缺口预警</Badge>}
                    {p.high_finance_dep && <Badge variant="warning">高融资依赖</Badge>}
                    {!p.gap_warning && !p.high_finance_dep && <Badge variant="success">合规</Badge>}
                    <Badge>{p.payload?.solver_status ?? "ok"}</Badge>
                  </div>
                  <div className="mt-2 border-t pt-2">
                    <AdoptButtons planId={p.id} status={p.status} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>安全垫曲线对比（每档基于自身 MinCash 乘子）</CardTitle>
              <CardDescription>余额 − 风险旋钮调整后的最低备付</CardDescription>
            </CardHeader>
            <CardContent>
              <CushionCompareChart plans={plans} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>演化余额曲线对比</CardTitle>
              <CardDescription>三档求解下每周末的现金余额 B[t]</CardDescription>
            </CardHeader>
            <CardContent>
              <BalanceCompareChart plans={plans} />
            </CardContent>
          </Card>

          {plans.map((p) => (
            <Card key={`actions-${p.id}`}>
              <CardHeader>
                <CardTitle>
                  <Badge variant={KNOB_TONE[p.risk_knob]} className="mr-2">
                    {KNOB_LABEL[p.risk_knob]}
                  </Badge>
                  PlanAction 明细（{p.actions.length}）
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DataTable
                  rows={p.actions}
                  columns={[
                    { header: "W", cell: (a) => a.week_t, align: "center", width: "3rem" },
                    {
                      header: "动作",
                      cell: (a) => (
                        <Badge variant={a.action === "invest" ? "primary" : "warning"}>
                          {ACTION_LABEL[a.action] ?? a.action}
                        </Badge>
                      ),
                      align: "center",
                    },
                    { header: "金额", cell: (a) => fmtMoney(a.amount), align: "right" },
                    {
                      header: "期限",
                      cell: (a) => (a.tenor_weeks ? `${a.tenor_weeks} 周` : "—"),
                      align: "center",
                    },
                    { header: "标的", cell: (a) => (a.notes ?? "").replace(/^(invest|finance):/, "") },
                  ]}
                  empty="此档无动作"
                />
              </CardContent>
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
