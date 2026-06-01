import { getServerSession } from "next-auth";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DataTable, fmtMoney } from "@/components/data-table";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

import { BalanceVsMinCashChart, NetCashFlowChart } from "./charts";
import { RunForecastButton } from "./run-button";

type ScenarioPayload = {
  net_cf: string[];
  balance: string[];
  safety_cushion: string[];
  lower_bound: (string | null)[];
  upper_bound: (string | null)[];
};

type ForecastPayload = {
  anchor: string;
  week_dates: string[];
  initial_balance: string;
  min_cash: string[];
  scenarios: { neutral: ScenarioPayload; pessimistic: ScenarioPayload };
  layer_breakdown: Record<
    string,
    Record<string, { inflow: string; outflow: string; net: string }>
  >;
  gap_warning_weeks: number[];
  near_breach_weeks: number[];
};

type ForecastResp = {
  id: string;
  entity_id: string;
  as_of_date: string;
  horizon_weeks: number;
  status: string;
  payload: ForecastPayload;
  created_at: string;
};

export default async function ForecastPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error -- extended session
  const token: string | undefined = session?.accessToken;

  let latest: ForecastResp | null = null;
  try {
    latest = await apiFetch<ForecastResp | null>("/api/v1/forecast/latest", { token });
  } catch {
    latest = null;
  }

  if (!latest) {
    return (
      <div className="flex flex-col gap-6">
        <header className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold">13 周预测看板</h1>
            <p className="text-sm text-muted-foreground">
              Phase 2 · 分层 + 双情景预测，含悲观情景缺口预警
            </p>
          </div>
          <RunForecastButton label="生成首份预测" />
        </header>
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p>当前主体尚无预测，请先在「数据录入」导入种子，再点右上角生成。</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const p = latest.payload;
  const weeks = p.week_dates.length;
  const neutralFinal = Number(p.scenarios.neutral.balance[weeks - 1]);
  const pessFinal = Number(p.scenarios.pessimistic.balance[weeks - 1]);
  const gap = p.gap_warning_weeks ?? [];
  const near = p.near_breach_weeks ?? [];

  const rows = Array.from({ length: weeks }, (_, i) => ({
    t: i + 1,
    date: p.week_dates[i],
    neutralNet: p.scenarios.neutral.net_cf[i],
    pessNet: p.scenarios.pessimistic.net_cf[i],
    minCash: p.min_cash[i],
    neutralBal: p.scenarios.neutral.balance[i],
    pessBal: p.scenarios.pessimistic.balance[i],
    pessCushion: p.scenarios.pessimistic.safety_cushion[i],
    flag: gap.includes(i + 1) ? "gap" : near.includes(i + 1) ? "near" : "ok",
  }));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">13 周预测看板</h1>
          <p className="text-sm text-muted-foreground">
            as-of {latest.as_of_date} · anchor {p.anchor} · 期初 ¥{Number(p.initial_balance).toLocaleString()}
            <span className="ml-2 text-xs">
              (forecast {latest.id.slice(0, 8)}... · {new Date(latest.created_at).toLocaleString("zh-CN")})
            </span>
          </p>
        </div>
        <RunForecastButton />
      </header>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>期末余额（中性）</CardDescription>
            <CardTitle className="text-primary">{fmtMoney(neutralFinal)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>期末余额（悲观）</CardDescription>
            <CardTitle className="text-warning">{fmtMoney(pessFinal)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>硬性缺口周</CardDescription>
            <CardTitle className={gap.length ? "text-destructive" : "text-success"}>
              {gap.length ? `W${gap.join(", W")}` : "无"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>擦边周（&lt;25% 备付）</CardDescription>
            <CardTitle className={near.length ? "text-warning" : "text-success"}>
              {near.length ? `W${near.join(", W")}` : "无"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>净现金流（中性 vs 悲观）</CardTitle>
          <CardDescription>橙色阴影 = uncertain 层 ±20% 区间</CardDescription>
        </CardHeader>
        <CardContent>
          <NetCashFlowChart payload={p} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>演化余额 vs 最低备付</CardTitle>
          <CardDescription>
            红虚线 = MinCash[t]，演化余额低于其连线即触发预警
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BalanceVsMinCashChart payload={p} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>13 周明细</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={rows}
            columns={[
              { header: "W", cell: (r) => r.t, align: "center", width: "3rem" },
              { header: "日期", cell: (r) => r.date },
              { header: "中性净CF", cell: (r) => fmtMoney(r.neutralNet), align: "right" },
              { header: "悲观净CF", cell: (r) => fmtMoney(r.pessNet), align: "right" },
              { header: "备付", cell: (r) => fmtMoney(r.minCash), align: "right" },
              { header: "中性余额", cell: (r) => fmtMoney(r.neutralBal), align: "right" },
              {
                header: "悲观余额",
                cell: (r) => (
                  <span className={Number(r.pessBal) < 0 ? "text-destructive" : ""}>
                    {fmtMoney(r.pessBal)}
                  </span>
                ),
                align: "right",
              },
              {
                header: "悲观安全垫",
                cell: (r) => (
                  <span
                    className={
                      Number(r.pessCushion) < 0
                        ? "font-semibold text-destructive"
                        : r.flag === "near"
                          ? "font-semibold text-warning"
                          : ""
                    }
                  >
                    {fmtMoney(r.pessCushion)}
                  </span>
                ),
                align: "right",
              },
              {
                header: "标签",
                cell: (r) =>
                  r.flag === "gap" ? (
                    <Badge variant="destructive">缺口</Badge>
                  ) : r.flag === "near" ? (
                    <Badge variant="warning">擦边</Badge>
                  ) : (
                    <Badge variant="success">OK</Badge>
                  ),
                align: "center",
              },
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
