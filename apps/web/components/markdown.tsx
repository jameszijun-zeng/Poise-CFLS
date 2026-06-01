"use client";

import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "@/components/code-block";
import { MermaidBlock } from "@/components/mermaid-block";
import { cn } from "@/lib/utils";

/**
 * 通用 Markdown 渲染器 —— 用于 chat assistant 气泡 & 任何需要展示 LLM 输出的位置。
 *
 * 支持：
 * - GFM：表格（含 sticky header）、删除线、任务列表、自动链接
 * - 软换行保留（remark-breaks）
 * - 代码块：highlight.js 语法高亮 + 一键复制
 * - mermaid 流程图：```mermaid``` fenced block 自动渲染
 * - 全文 tabular-nums（金额/百分比对齐美观）
 */
export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={cn("markdown-body text-sm leading-relaxed", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          // ---- 标题 ----
          h1: ({ children }) => (
            <h1 className="mb-2 mt-3 text-lg font-bold text-foreground">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-3 border-b border-border pb-1 text-base font-semibold text-foreground">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1.5 mt-2.5 text-[15px] font-semibold text-foreground">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="mb-1 mt-2 text-sm font-semibold text-foreground">{children}</h4>
          ),

          // ---- 段落 ----
          p: ({ children }) => (
            <p className="my-1.5 text-foreground/90">{children}</p>
          ),

          // ---- 列表 ----
          ul: ({ children }) => (
            <ul className="my-1.5 ml-4 list-disc space-y-1 text-foreground/90 marker:text-muted-foreground">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-1.5 ml-4 list-decimal space-y-1 text-foreground/90 marker:text-muted-foreground">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="pl-1">{children}</li>,

          // ---- 强调 ----
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          del: ({ children }) => (
            <del className="text-muted-foreground line-through">{children}</del>
          ),

          // ---- 代码（行内 / fenced 区分 + mermaid 拦截） ----
          code: ({ inline, className, children, ...props }: any) => {
            const match = /language-(\w+)/.exec(className || "");
            const lang = match?.[1];
            const text = String(children).replace(/\n$/, "");

            if (inline) {
              return (
                <code
                  className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-primary"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            // mermaid 流程图
            if (lang === "mermaid") {
              return <MermaidBlock code={text} />;
            }
            // 普通代码块：highlight.js 高亮
            return <CodeBlock code={text} lang={lang} />;
          },
          // ReactMarkdown 默认会用 <pre> 包裹 fenced code；我们的 CodeBlock 已自带 <pre>，故穿透
          pre: ({ children }) => <>{children}</>,

          // ---- 引用 ----
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-4 border-primary/40 bg-primary/5 px-3 py-1.5 text-foreground/80">
              {children}
            </blockquote>
          ),

          // ---- 分割线 ----
          hr: () => <hr className="my-3 border-border" />,

          // ---- 链接 ----
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),

          // ---- 表格（sticky header + zebra + 滚动容器） ----
          table: ({ children }) => (
            <div className="table-scroll my-2 overflow-x-auto rounded-md border">
              <table className="w-full border-collapse text-[13px]">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b bg-muted/80 text-xs uppercase text-muted-foreground backdrop-blur supports-[backdrop-filter]:bg-muted/60">
              {children}
            </thead>
          ),
          tr: ({ children }) => (
            <tr className="border-b border-border/50 last:border-b-0 even:bg-muted/20">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-3 py-1.5 text-left font-medium">{children}</th>
          ),
          td: ({ children }) => <td className="px-3 py-1.5">{children}</td>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
