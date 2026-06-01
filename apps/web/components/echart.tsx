"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

import { cn } from "@/lib/utils";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function ECharts({
  option,
  height = 320,
  className,
}: {
  option: EChartsOption;
  height?: number;
  className?: string;
}) {
  return (
    <div className={cn("w-full", className)}>
      <ReactECharts
        option={option}
        style={{ height, width: "100%" }}
        notMerge
        opts={{ renderer: "canvas" }}
      />
    </div>
  );
}
