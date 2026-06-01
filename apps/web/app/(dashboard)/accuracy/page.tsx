import { getServerSession } from "next-auth";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DataTable } from "@/components/data-table";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

import { MapeBarChart } from "./mape-chart";
import { TriggerRollingButton } from "./trigger-button";

type AccuracyResp = {
  by_layer: { layer: string; sample_count: number; mape: string | null }[];
  by_category: { category: string; sample_count: number; mape: string | null }[];
  note?: string;
};

type RollingRun = {
  id: string;
  triggered_at: string;
  triggered_by: string | null;
  week_start: string;
  status: string;
  forecast_id: string | null;
  summary: string | null;
  mape_by_layer: { items: { layer: string; sample_count: number; mape: string | null }[] } | null;
};

type BiasCorrection = {
  id: number;
  category: string;
  direction: string;
  multiplier: string;
  samples: number;
  updated_at: string;
};

const LAYER_LABEL: Record<string, string> = {
  deterministic: "确定层 (W1-4)",
  pattern: "规律层 (W5-8)",
  uncertain: "不确定层 (W9-13)",
};
const CATEGORY_LABEL: Record<string, string> = {
  sales_collection: "销售回款",
  purchase_payment: "采购付款",
  payroll: "薪酬",
  tax: "税费",
  rent: "租金",
  interest: "利息",
  principal_repay: "还本",
  other: "其他",
};

const ACC_TONE = (m: string | null): "success" | "primary" | "warning" | "destructive" | "default" => {
  if (m == null) return "default";
  const v = Number(m) * 100;
  if (v < 5) return "success";
  if (v < 15) return "primary";
  if (v < 30) return "warning";
  return "destructive";
};

export default async function AccuracyPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [acc, runs, bias] = await Promise.all([
    apiFetch<AccuracyResp>("/api/v1/forecast/accuracy/summary", { token }).catch(
      () => ({ by_layer: [], by_category: [] }) as AccuracyResp,
    ),
    apiFetch<RollingRun[]>("/api/v1/feedback/rolling-runs?limit=10", { token }).catch(() => []),
    apiFetch<BiasCorrection[]>("/api/v1/feedback/bias-corrections", { token }).catch(() => []),
  ]);

  const totalSamples = acc.by_layer.reduce((s, b) => s + b.sample_count, 0);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">MAPE 看板 & 反馈学习</h1>
          <p className="text-sm text-muted-foreground">
            Phase 6 · 分层与分类预测准确度 · 每周一 06:00 自动滚动重跑 · 系统性偏差 EMA 校正
          </p>
        </div>
        <TriggerRollingButton />
      </header>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>(forecast, actual) 样本对</CardDescription>
            <CardTitle>{totalSamples}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>滚动重跑总次数</CardDescription>
            <CardTitle>{runs.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>偏差校正系数</CardDescription>
            <CardTitle>{bias.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>最近重跑</CardDescription>
            <CardTitle className="text-base">
              {runs[0]
                ? new Date(runs[0].triggered_at).toLocaleString("zh-CN")
                : "无"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {totalSamples === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            还没有 (forecast, actual) 样本。点右上角"手动触发滚动重跑"生成首批数据。
          </CardContent>
        </Card>
      )}

      {totalSamples > 0 && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>按分层 MAPE</CardTitle>
                <CardDescription>近端严、远端考核区间命中率</CardDescription>
              </CardHeader>
              <CardContent>
                <MapeBarChart buckets={acc.by_layer} kind="layer" />
                <DataTable
                  className="mt-3"
                  rows={acc.by_layer}
                  columns={[
                    { header: "分层", cell: (r) => LAYER_LABEL[r.layer] ?? r.layer },
                    { header: "样本", cell: (r) => r.sample_count, align: "right" },
                    {
                      header: "MAPE",
                      cell: (r) =>
                        r.mape ? (
                          <Badge variant={ACC_TONE(r.mape)}>
                            {(Number(r.mape) * 100).toFixed(2)}%
                          </Badge>
                        ) : (
                          "—"
                        ),
                      align: "right",
                    },
                  ]}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>按收支类 MAPE</CardTitle>
              </CardHeader>
              <CardContent>
                <MapeBarChart buckets={acc.by_category} kind="category" />
                <DataTable
                  className="mt-3"
                  rows={acc.by_category}
                  columns={[
                    { header: "类别", cell: (r) => CATEGORY_LABEL[r.category] ?? r.category },
                    { header: "样本", cell: (r) => r.sample_count, align: "right" },
                    {
                      header: "MAPE",
                      cell: (r) =>
                        r.mape ? (
                          <Badge variant={ACC_TONE(r.mape)}>
                            {(Number(r.mape) * 100).toFixed(2)}%
                          </Badge>
                        ) : (
                          "—"
                        ),
                      align: "right",
                    },
                  ]}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>偏差校正系数（EMA 平滑）</CardTitle>
              <CardDescription>
                forecast_corrected = forecast_raw × multiplier · α = 0.3 · 取值范围 [0.5, 1.5]
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DataTable
                rows={bias}
                columns={[
                  { header: "类别", cell: (r) => CATEGORY_LABEL[r.category] ?? r.category },
                  {
                    header: "方向",
                    cell: (r) => (
                      <Badge variant={r.direction === "inflow" ? "success" : "warning"}>
                        {r.direction === "inflow" ? "收" : "付"}
                      </Badge>
                    ),
                    align: "center",
                  },
                  {
                    header: "校正系数",
                    cell: (r) => {
                      const v = Number(r.multiplier);
                      const dev = Math.abs(v - 1) * 100;
                      const tone =
                        dev < 2 ? "success" : dev < 10 ? "primary" : dev < 25 ? "warning" : "destructive";
                      return (
                        <Badge variant={tone}>
                          {v.toFixed(4)}
                          {v > 1 ? " ↑" : v < 1 ? " ↓" : ""}
                        </Badge>
                      );
                    },
                    align: "right",
                  },
                  { header: "累计样本", cell: (r) => r.samples, align: "right" },
                  {
                    header: "更新时间",
                    cell: (r) => new Date(r.updated_at).toLocaleString("zh-CN"),
                    align: "right",
                  },
                ]}
                empty="尚无偏差校正记录"
              />
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>滚动重跑历史（最近 10 次）</CardTitle>
          <CardDescription>scheduler = Celery Beat 自动触发 · 用户名 = 手动触发</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={runs}
            columns={[
              {
                header: "触发时间",
                cell: (r) => new Date(r.triggered_at).toLocaleString("zh-CN"),
              },
              {
                header: "触发者",
                cell: (r) => r.triggered_by ?? "scheduler",
                align: "center",
              },
              { header: "目标周起", cell: (r) => r.week_start },
              {
                header: "状态",
                cell: (r) => <Badge variant="success">{r.status}</Badge>,
                align: "center",
              },
              {
                header: "新预测",
                cell: (r) =>
                  r.forecast_id ? (
                    <code className="text-xs">{r.forecast_id.slice(0, 8)}...</code>
                  ) : (
                    "—"
                  ),
                align: "center",
              },
              { header: "摘要", cell: (r) => <span className="text-xs">{r.summary ?? ""}</span> },
            ]}
            empty="尚无滚动重跑记录"
          />
        </CardContent>
      </Card>
    </div>
  );
}
