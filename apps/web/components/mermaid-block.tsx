"use client";

import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Mermaid 流程图渲染。
 * 在 markdown 中 ```mermaid ... ``` 代码块识别后调用此组件。
 *
 * 设计：
 * - 延迟加载 mermaid 包，避免首屏体积
 * - 主题用 `default`，颜色变量与稳盈主色对齐
 * - 渲染失败时 fallback 显示原始 code 块
 */
export function MermaidBlock({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // 每个实例独立 id，避免同页多图冲突
  const reactId = useId();
  const renderId = `m${reactId.replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "base",
          securityLevel: "loose",
          fontFamily: "inherit",
          themeVariables: {
            primaryColor: "#2563EB",
            primaryTextColor: "#0F172A",
            primaryBorderColor: "#1E3A8A",
            lineColor: "#64748B",
            secondaryColor: "#DBEAFE",
            tertiaryColor: "#F8FAFC",
          },
        });
        const { svg } = await mermaid.render(renderId, code);
        if (!cancelled) setSvg(svg);
      } catch (e) {
        if (!cancelled) setErr(String(e instanceof Error ? e.message : e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, renderId]);

  if (err) {
    return (
      <div className="my-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs">
        <div className="mb-1 font-medium text-destructive">mermaid 渲染失败</div>
        <div className="mb-2 text-muted-foreground">{err}</div>
        <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-[11px]">{code}</pre>
      </div>
    );
  }
  if (!svg) {
    return (
      <div className="my-2 flex items-center gap-2 rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
        正在渲染流程图...
      </div>
    );
  }
  return (
    <div
      ref={ref}
      className={cn("my-3 flex justify-center overflow-x-auto rounded-md border bg-muted/20 p-3")}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
