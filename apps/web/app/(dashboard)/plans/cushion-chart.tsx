"use client";

import type { EChartsOption } from "echarts";

import { ECharts } from "@/components/echart";

type Plan = {
  risk_knob: string;
  safety_cushion_curve: (string | number)[] | null;
  payload?: { balance_curve?: string[] } | null;
};

const KNOB_LABEL: Record<string, string> = {
  conservative: "稳健",
  balanced: "折中",
  aggressive: "进取",
};
const KNOB_COLOR: Record<string, string> = {
  conservative: "#16a34a",
  balanced: "#2563eb",
  aggressive: "#ea580c",
};

const fmtMillion = (v: number) => `${(v / 1e6).toFixed(1)}M`;

export function CushionCompareChart({ plans }: { plans: Plan[] }) {
  const horizon = Math.max(...plans.map((p) => p.safety_cushion_curve?.length ?? 0));
  const xLabels = Array.from({ length: horizon }, (_, i) => `W${i + 1}`);

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (typeof v === "number" ? fmtMillion(v) : String(v)),
    },
    legend: { top: 4, data: plans.map((p) => KNOB_LABEL[p.risk_knob] ?? p.risk_knob) },
    grid: { left: 50, right: 25, top: 40, bottom: 40 },
    xAxis: { type: "category", data: xLabels },
    yAxis: { type: "value", axisLabel: { formatter: fmtMillion }, splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } } },
    series: plans.map((p) => ({
      name: KNOB_LABEL[p.risk_knob] ?? p.risk_knob,
      type: "line",
      smooth: true,
      data: (p.safety_cushion_curve ?? []).map((v) => Number(v)),
      color: KNOB_COLOR[p.risk_knob],
      symbol: "circle",
      lineStyle: { width: 2 },
    })),
  };

  return <ECharts option={option} height={280} />;
}

export function BalanceCompareChart({ plans }: { plans: Plan[] }) {
  const horizon = Math.max(...plans.map((p) => p.payload?.balance_curve?.length ?? 0));
  const xLabels = Array.from({ length: horizon }, (_, i) => `W${i + 1}`);

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (typeof v === "number" ? fmtMillion(v) : String(v)),
    },
    legend: { top: 4, data: plans.map((p) => KNOB_LABEL[p.risk_knob] ?? p.risk_knob) },
    grid: { left: 50, right: 25, top: 40, bottom: 40 },
    xAxis: { type: "category", data: xLabels },
    yAxis: { type: "value", axisLabel: { formatter: fmtMillion }, splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } } },
    series: plans.map((p) => ({
      name: KNOB_LABEL[p.risk_knob] ?? p.risk_knob,
      type: "line",
      smooth: true,
      data: (p.payload?.balance_curve ?? []).map((v) => Number(v)),
      color: KNOB_COLOR[p.risk_knob],
      symbol: "circle",
      lineStyle: { width: 2 },
    })),
  };

  return <ECharts option={option} height={280} />;
}
