"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * 代码块语法高亮（highlight.js）+ 一键复制。
 * 延迟加载 highlight.js 主题 CSS。
 */
const LANG_ALIAS: Record<string, string> = {
  ts: "typescript",
  js: "javascript",
  py: "python",
  sh: "bash",
  shell: "bash",
  yml: "yaml",
};

export function CodeBlock({
  code,
  lang,
}: {
  code: string;
  lang?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);
  const normalized = lang ? LANG_ALIAS[lang.toLowerCase()] ?? lang.toLowerCase() : "";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const hljs = (await import("highlight.js")).default;
      if (cancelled || !ref.current) return;
      if (normalized && hljs.getLanguage(normalized)) {
        const r = hljs.highlight(code, { language: normalized, ignoreIllegals: true });
        ref.current.innerHTML = r.value;
      } else {
        const r = hljs.highlightAuto(code);
        ref.current.innerHTML = r.value;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, normalized]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }

  return (
    <div className="group relative my-2 overflow-hidden rounded-md border bg-[#0F172A]">
      {normalized && (
        <div className="flex items-center justify-between border-b border-white/10 px-3 py-1 text-[10px] uppercase tracking-wider text-white/60">
          <span>{normalized}</span>
          <button
            onClick={copy}
            className="opacity-0 transition-opacity hover:text-white group-hover:opacity-100"
          >
            {copied ? "✓ 已复制" : "复制"}
          </button>
        </div>
      )}
      <pre className="overflow-x-auto p-3">
        <code
          ref={ref}
          className={cn("font-mono text-[12px] leading-relaxed text-white/90", `language-${normalized}`)}
        >
          {code}
        </code>
      </pre>
    </div>
  );
}
