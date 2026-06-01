"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type Phase =
  | "connecting"   // 已点发送，等首个 SSE
  | "thinking"     // 流式 reasoning 中
  | "tool_calling" // tool 调用执行中
  | "writing"      // 最终回答 token 涌出中
  | "done"
  | "error";

export type TimelineStep =
  | { kind: "phase"; phase: Phase; at: number; label?: string }
  | { kind: "tool"; name: string; at: number; status: "running" | "done"; resultKeys?: string[] };

const TOOL_LABEL: Record<string, string> = {
  run_forecast: "运行预测",
  build_and_solve: "求解三档方案",
  explain_plan: "解释方案",
  diagnose_infeasible: "诊断缺口",
  apply_overrides: "解析假设",
  query_position: "查询头寸",
};

const PHASE_META: Record<Phase, { label: string; icon: string; dotClass: string }> = {
  connecting:   { label: "建立连接",   icon: "🔌", dotClass: "bg-muted-foreground/60" },
  thinking:     { label: "深度推理中", icon: "🧠", dotClass: "bg-primary animate-pulse" },
  tool_calling: { label: "调用工具",   icon: "🔧", dotClass: "bg-warning animate-pulse" },
  writing:      { label: "撰写答复",   icon: "✏️", dotClass: "bg-success animate-pulse" },
  done:         { label: "完成",       icon: "✓",  dotClass: "bg-success" },
  error:        { label: "失败",       icon: "✗",  dotClass: "bg-destructive" },
};

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function ThinkingPanel({
  phase,
  startedAt,
  steps,
  reasoning,
}: {
  phase: Phase;
  startedAt: number;
  steps: TimelineStep[];
  reasoning: string;
}) {
  // 实时计时器（每 0.5s 触发 re-render）
  const [, force] = useState({});
  useEffect(() => {
    if (phase === "done" || phase === "error") return;
    const t = setInterval(() => force({}), 500);
    return () => clearInterval(t);
  }, [phase]);

  // 推理区自动滚到底
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [reasoning]);

  const elapsed = Date.now() - startedAt;
  const meta = PHASE_META[phase];

  // tool 步骤汇总展示
  const toolSteps = steps.filter((s): s is Extract<TimelineStep, { kind: "tool" }> => s.kind === "tool");

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-background/80 px-3 py-2.5 shadow-sm backdrop-blur">
      {/* 顶部状态行 */}
      <div className="flex items-center gap-2 text-xs">
        <span className={cn("inline-block h-2.5 w-2.5 rounded-full", meta.dotClass)} />
        <span className="font-medium text-foreground">
          {meta.icon} {meta.label}
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="tabular-nums text-muted-foreground">{fmtMs(elapsed)}</span>
        {reasoning && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="tabular-nums text-muted-foreground">推理 {reasoning.length} 字</span>
          </>
        )}
        {toolSteps.length > 0 && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="tabular-nums text-muted-foreground">
              工具 {toolSteps.filter((t) => t.status === "done").length}/{toolSteps.length}
            </span>
          </>
        )}
      </div>

      {/* tool 时间线 */}
      {toolSteps.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-border/50 pt-2">
          {toolSteps.map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span
                className={cn(
                  "inline-block h-1.5 w-1.5 rounded-full",
                  t.status === "running"
                    ? "bg-warning animate-pulse"
                    : "bg-success",
                )}
              />
              <span className="tabular-nums text-muted-foreground">
                {fmtMs(t.at - startedAt)}
              </span>
              <Badge variant={t.status === "running" ? "warning" : "success"}>
                {TOOL_LABEL[t.name] ?? t.name}
              </Badge>
              {t.status === "done" && t.resultKeys && (
                <span className="truncate text-[10px] text-muted-foreground">
                  → {t.resultKeys.slice(0, 4).join(", ")}
                  {t.resultKeys.length > 4 && "..."}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 实时推理流 */}
      {reasoning && (
        <details className="border-t border-border/50 pt-2 text-[11px]" open>
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            🧠 思考流（实时）
          </summary>
          <div
            ref={scroller}
            className="mt-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/40 p-2 leading-relaxed text-muted-foreground"
          >
            {reasoning}
            <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-primary align-middle" />
          </div>
        </details>
      )}
    </div>
  );
}
