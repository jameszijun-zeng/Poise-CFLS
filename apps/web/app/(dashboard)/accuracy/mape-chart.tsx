"use client";

import type { EChartsOption } from "echarts";

import { ECharts } from "@/components/echart";

type Bucket = { layer?: string; category?: string; sample_count: number; mape: number | string | null };

const LAYER_LABEL: Record<string, string> = {
  deterministic: "确定层",
  pattern: "规律层",
  uncertain: "不确定层",
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

export function MapeBarChart({ buckets, kind }: { buckets: Bucket[]; kind: "layer" | "category" }) {
  const labels = buckets.map((b) =>
    kind === "layer" ? LAYER_LABEL[b.layer ?? ""] ?? b.layer ?? "—" : CATEGORY_LABEL[b.category ?? ""] ?? b.category ?? "—",
  );
  const values = buckets.map((b) => (b.mape == null ? 0 : Number(b.mape) * 100));
  const samples = buckets.map((b) => b.sample_count);

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      formatter: (params) => {
        const arr = Array.isArray(params) ? params : [params];
        const p = arr[0];
        const idx = p.dataIndex ?? 0;
        return `${labels[idx]}<br/>MAPE: ${values[idx].toFixed(2)}%<br/>样本: ${samples[idx]}`;
      },
    },
    grid: { left: 50, right: 20, top: 20, bottom: 50 },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { rotate: kind === "category" ? 30 : 0, fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => `${v.toFixed(1)}%` },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: {
          color: (params) => {
            const v = (params.value as number) ?? 0;
            if (v < 5) return "#16a34a";
            if (v < 15) return "#2563eb";
            if (v < 30) return "#f59e0b";
            return "#dc2626";
          },
        },
        label: {
          show: true,
          position: "top",
          formatter: (p) => `${(p.value as number).toFixed(1)}%`,
          fontSize: 11,
        },
      },
    ],
  };
  return <ECharts option={option} height={260} />;
}
