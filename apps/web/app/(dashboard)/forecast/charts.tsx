"use client";

import type { EChartsOption } from "echarts";

import { ECharts } from "@/components/echart";

type ForecastPayload = {
  anchor: string;
  week_dates: string[];
  initial_balance: string;
  min_cash: string[];
  scenarios: {
    neutral: {
      net_cf: string[];
      balance: string[];
      safety_cushion: string[];
      lower_bound: (string | null)[];
      upper_bound: (string | null)[];
    };
    pessimistic: {
      net_cf: string[];
      balance: string[];
      safety_cushion: string[];
      lower_bound: (string | null)[];
      upper_bound: (string | null)[];
    };
  };
  gap_warning_weeks: number[];
  near_breach_weeks: number[];
};

const toNumArr = (a: string[]) => a.map((s) => Number(s));
const toNullableNumArr = (a: (string | null)[]) =>
  a.map((s) => (s === null ? null : Number(s)));

const colors = {
  neutral: "#2563eb",
  pessimistic: "#ea580c",
  minCash: "#dc2626",
  band: "rgba(234, 88, 12, 0.12)",
};

const fmtMillion = (v: number) => `${(v / 1e6).toFixed(1)}M`;

function weekLabels(p: ForecastPayload): string[] {
  return p.week_dates.map((d, i) => `W${i + 1}\n${d.slice(5)}`);
}

export function NetCashFlowChart({ payload }: { payload: ForecastPayload }) {
  const xLabels = weekLabels(payload);
  const neutralNet = toNumArr(payload.scenarios.neutral.net_cf);
  const pessNet = toNumArr(payload.scenarios.pessimistic.net_cf);
  const pessLower = toNullableNumArr(payload.scenarios.pessimistic.lower_bound);
  const pessUpper = toNullableNumArr(payload.scenarios.pessimistic.upper_bound);
  const bandLower = pessLower.map((v, i) => (v ?? pessNet[i]));
  const bandWidth = pessUpper.map((v, i) => (v ?? pessNet[i]) - bandLower[i]);

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (typeof v === "number" ? fmtMillion(v) : String(v)),
    },
    legend: { top: 4, data: ["中性 净CF", "悲观 净CF", "悲观区间下界", "悲观区间上界"] },
    grid: { left: 50, right: 25, top: 40, bottom: 50 },
    xAxis: {
      type: "category",
      data: xLabels,
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: fmtMillion },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: [
      {
        name: "悲观区间下界",
        type: "line",
        data: bandLower,
        lineStyle: { opacity: 0 },
        symbol: "none",
        stack: "band",
        showInLegend: false,
      },
      {
        name: "悲观区间宽度",
        type: "line",
        data: bandWidth,
        lineStyle: { opacity: 0 },
        symbol: "none",
        stack: "band",
        areaStyle: { color: colors.band },
        showInLegend: false,
      },
      {
        name: "中性 净CF",
        type: "line",
        data: neutralNet,
        color: colors.neutral,
        smooth: true,
        symbol: "circle",
      },
      {
        name: "悲观 净CF",
        type: "line",
        data: pessNet,
        color: colors.pessimistic,
        smooth: true,
        lineStyle: { type: "dashed" },
        symbol: "circle",
      },
    ],
  };

  return <ECharts option={option} height={320} />;
}

export function BalanceVsMinCashChart({ payload }: { payload: ForecastPayload }) {
  const xLabels = weekLabels(payload);
  const neutralBal = toNumArr(payload.scenarios.neutral.balance);
  const pessBal = toNumArr(payload.scenarios.pessimistic.balance);
  const minCash = toNumArr(payload.min_cash);

  const gapSet = new Set(payload.gap_warning_weeks);
  const nearSet = new Set(payload.near_breach_weeks);

  const markPointData = [
    ...payload.gap_warning_weeks.map((t) => ({
      coord: [xLabels[t - 1], pessBal[t - 1]],
      value: "缺口",
      itemStyle: { color: "#dc2626" },
    })),
    ...payload.near_breach_weeks.map((t) => ({
      coord: [xLabels[t - 1], pessBal[t - 1]],
      value: "擦边",
      itemStyle: { color: "#f59e0b" },
    })),
  ];

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (typeof v === "number" ? fmtMillion(v) : String(v)),
    },
    legend: { top: 4, data: ["中性 余额", "悲观 余额", "最低备付 MinCash"] },
    grid: { left: 50, right: 25, top: 40, bottom: 50 },
    xAxis: {
      type: "category",
      data: xLabels,
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: fmtMillion },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: [
      {
        name: "最低备付 MinCash",
        type: "line",
        data: minCash,
        color: colors.minCash,
        symbol: "none",
        lineStyle: { type: "dotted", width: 2 },
        areaStyle: { color: "rgba(220, 38, 38, 0.08)" },
      },
      {
        name: "中性 余额",
        type: "line",
        data: neutralBal,
        color: colors.neutral,
        smooth: true,
        symbol: "circle",
      },
      {
        name: "悲观 余额",
        type: "line",
        data: pessBal,
        color: colors.pessimistic,
        smooth: true,
        lineStyle: { type: "dashed" },
        symbol: "circle",
        markPoint: markPointData.length
          ? { data: markPointData, symbolSize: 50, label: { fontSize: 10, color: "#fff" } }
          : undefined,
      },
    ],
  };

  return <ECharts option={option} height={340} />;
}
