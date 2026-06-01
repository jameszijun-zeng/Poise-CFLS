"use client";

import type { EChartsOption } from "echarts";

import { ECharts } from "@/components/echart";

type Payload = {
  week_dates?: string[];
  min_cash?: string[];
  scenarios?: {
    neutral?: { balance?: string[] };
    pessimistic?: { balance?: string[] };
  };
  gap_warning_weeks?: number[];
  near_breach_weeks?: number[];
};

const fmtMillion = (v: number) => `${(v / 1e6).toFixed(0)}M`;

export function ForecastMiniChart({ payload }: { payload: Payload }) {
  const horizon = payload.week_dates?.length ?? 0;
  const x = Array.from({ length: horizon }, (_, i) => `W${i + 1}`);
  const neutral = (payload.scenarios?.neutral?.balance ?? []).map(Number);
  const pess = (payload.scenarios?.pessimistic?.balance ?? []).map(Number);
  const minCash = (payload.min_cash ?? []).map(Number);

  const gap = new Set(payload.gap_warning_weeks ?? []);
  const near = new Set(payload.near_breach_weeks ?? []);
  const markPoints = [
    ...[...gap].map((w) => ({
      coord: [`W${w}`, pess[w - 1]],
      itemStyle: { color: "#dc2626" },
      symbol: "circle",
      symbolSize: 14,
      value: "缺",
    })),
    ...[...near].map((w) => ({
      coord: [`W${w}`, pess[w - 1]],
      itemStyle: { color: "#f59e0b" },
      symbol: "circle",
      symbolSize: 14,
      value: "擦",
    })),
  ];

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) =>
        typeof v === "number" ? `¥${(v / 1e6).toFixed(1)}M` : String(v),
    },
    grid: { left: 45, right: 15, top: 25, bottom: 25 },
    xAxis: {
      type: "category",
      data: x,
      axisLabel: { fontSize: 10, color: "#64748B" },
      axisLine: { lineStyle: { color: "#CBD5E1" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: fmtMillion, fontSize: 10, color: "#64748B" },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: [
      {
        name: "最低备付",
        type: "line",
        data: minCash,
        color: "#dc2626",
        symbol: "none",
        lineStyle: { type: "dotted", width: 1.5 },
        areaStyle: { color: "rgba(220, 38, 38, 0.05)" },
      },
      {
        name: "中性",
        type: "line",
        data: neutral,
        color: "#2563eb",
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2 },
      },
      {
        name: "悲观",
        type: "line",
        data: pess,
        color: "#ea580c",
        smooth: true,
        symbol: "none",
        lineStyle: { type: "dashed", width: 2 },
        markPoint: markPoints.length
          ? { data: markPoints as never, label: { fontSize: 9, color: "#fff" } }
          : undefined,
      },
    ],
  };

  return <ECharts option={option} height={200} />;
}
