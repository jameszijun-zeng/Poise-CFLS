import { getServerSession } from "next-auth";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

type Forecast = {
  id: string;
  as_of_date: string;
  payload: {
    gap_warning_weeks?: number[];
    near_breach_weeks?: number[];
    high_finance_dep_weeks?: number[];
    week_dates?: string[];
  } | null;
};

type Plan = {
  id: string;
  risk_knob: string;
  status: string;
  gap_warning: boolean;
  high_finance_dep: boolean;
  payload: { gap_warning_weeks?: number[]; finance_dep_ratio?: number } | null;
};

const KNOB_LABEL: Record<string, string> = {
  conservative: "稳健",
  balanced: "折中",
  aggressive: "进取",
};

export default async function AlertsPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  let forecast: Forecast | null = null;
  let plans: Plan[] = [];
  try {
    forecast = await apiFetch<Forecast | null>("/api/v1/forecast/latest", { token });
  } catch {}
  if (forecast) {
    try {
      plans = await apiFetch<Plan[]>(`/api/v1/plans/by-forecast/${forecast.id}`, { token });
    } catch {}
  }

  const fc = forecast?.payload ?? {};
  const dates = fc.week_dates ?? [];
  const gaps = fc.gap_warning_weeks ?? [];
  const nears = fc.near_breach_weeks ?? [];
  const planGaps = plans.flatMap((p) =>
    (p.payload?.gap_warning_weeks ?? []).map((w) => ({ week: w, risk_knob: p.risk_knob })),
  );
  const highDepPlans = plans.filter((p) => p.high_finance_dep);

  const totalAlerts = gaps.length + nears.length + planGaps.length + highDepPlans.length;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">预警中心</h1>
        <p className="text-sm text-muted-foreground">
          聚合预测引擎（悲观情景）与决策引擎（求解结果）的所有风险标签
          {forecast && (
            <span className="ml-2 text-xs">
              · 基于预测 {forecast.id.slice(0, 8)}... · as-of {forecast.as_of_date}
            </span>
          )}
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>预警总数</CardDescription>
            <CardTitle className={totalAlerts > 0 ? "text-warning" : "text-success"}>
              {totalAlerts}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>悲观情景硬缺口周</CardDescription>
            <CardTitle className={gaps.length ? "text-destructive" : "text-success"}>
              {gaps.length || "无"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>悲观情景擦边周</CardDescription>
            <CardTitle className={nears.length ? "text-warning" : "text-success"}>
              {nears.length || "无"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>高融资依赖方案</CardDescription>
            <CardTitle className={highDepPlans.length ? "text-warning" : "text-success"}>
              {highDepPlans.length || "无"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>悲观情景缺口预警（来自预测引擎）</CardTitle>
          <CardDescription>
            按系统设计 §3.7：B_pess[t] - MinCash[t] {`<`} 0 触发硬性预警 ·{" "}
            {`<`} 25% × MinCash 触发擦边
          </CardDescription>
        </CardHeader>
        <CardContent>
          {gaps.length === 0 && nears.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">悲观情景下安全垫健康，无预警。</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {gaps.map((w) => (
                <li key={`g-${w}`} className="flex items-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                  <Badge variant="destructive">硬缺口</Badge>
                  <span className="font-medium">
                    W{w} ({dates[w - 1]})
                  </span>
                  <span className="text-muted-foreground">
                    悲观情景下安全垫为负 —— 即使全额动用授信也可能突破备付底线
                  </span>
                </li>
              ))}
              {nears.map((w) => (
                <li key={`n-${w}`} className="flex items-center gap-3 rounded-md border border-warning/40 bg-warning/5 p-3">
                  <Badge variant="warning">擦边</Badge>
                  <span className="font-medium">
                    W{w} ({dates[w - 1]})
                  </span>
                  <span className="text-muted-foreground">
                    悲观情景下安全垫低于 25% × MinCash，需关注备付压力
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>决策引擎风险标签（按求解结果）</CardTitle>
          <CardDescription>三档方案的缺口与融资依赖度</CardDescription>
        </CardHeader>
        <CardContent>
          {plans.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">尚未求解。在「方案对比」点击求解后这里会汇总各档风险。</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {plans.map((p) => {
                const issues: { label: string; tone: "destructive" | "warning" }[] = [];
                if (p.gap_warning) issues.push({ label: "求解后仍有缺口", tone: "destructive" });
                if (p.high_finance_dep) issues.push({ label: `融资依赖 ${((p.payload?.finance_dep_ratio ?? 0) * 100).toFixed(0)}%`, tone: "warning" });
                if (issues.length === 0) return null;
                return (
                  <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-md border p-3">
                    <span className="font-medium">{KNOB_LABEL[p.risk_knob] ?? p.risk_knob}</span>
                    <span className="text-xs text-muted-foreground">{p.id.slice(0, 8)}...</span>
                    {issues.map((i, k) => (
                      <Badge key={k} variant={i.tone}>
                        {i.label}
                      </Badge>
                    ))}
                  </li>
                );
              })}
              {plans.every((p) => !p.gap_warning && !p.high_finance_dep) && (
                <li className="rounded-md border border-success/30 bg-success/5 p-3 text-success">
                  ✓ 三档方案均无求解后缺口、无高融资依赖
                </li>
              )}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
