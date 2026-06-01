"use client";

import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/markdown";
import { cn } from "@/lib/utils";

import { ThinkingPanel, type Phase, type TimelineStep } from "./thinking-panel";

type ConvSummary = {
  id: string;
  title: string | null;
  updated_at: string;
};

type Msg = {
  id: number;
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  reasoning_content: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: Record<string, unknown> | null;
  model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: string;
};

type FullConv = {
  id: string;
  title: string | null;
  messages: Msg[];
};

const TOOL_LABEL: Record<string, string> = {
  run_forecast: "运行预测",
  build_and_solve: "求解方案",
  explain_plan: "解释方案",
  diagnose_infeasible: "诊断缺口",
  apply_overrides: "解析假设",
  query_position: "查询头寸",
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export function ChatUI() {
  const { data: session } = useSession();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [convList, setConvList] = useState<ConvSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [conv, setConv] = useState<FullConv | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 流式态：phase + timeline 步骤 + 推理 + 答复
  const [phase, setPhase] = useState<Phase>("connecting");
  const [stepStartAt, setStepStartAt] = useState<number>(Date.now());
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [streamingReasoning, setStreamingReasoning] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  // 拉会话列表
  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/api/v1/chat/conversations`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setConvList)
      .catch(() => {});
  }, [token, busy]);

  // 拉激活会话的完整消息
  useEffect(() => {
    if (!token || !activeId) {
      setConv(null);
      return;
    }
    fetch(`${API_BASE}/api/v1/chat/conversations/${activeId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((c) => setConv(c))
      .catch(() => {});
  }, [token, activeId, busy]);

  // 滚到底
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conv]);

  async function send() {
    if (!input.trim() || !token || busy) return;
    const t0 = Date.now();
    setBusy(true);
    setError(null);
    setStreamingText("");
    setStreamingReasoning("");
    setSteps([]);
    setPhase("connecting");
    setStepStartAt(t0);
    const userText = input;
    setInput("");
    try {
      const res = await fetch(`${API_BASE}/api/v1/chat/turn-stream`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: activeId,
          message: userText,
        }),
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let textAcc = "";
      let reasoningAcc = "";
      const stepsAcc: TimelineStep[] = [];
      let newConvId: string | null = null;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const raw = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 2);
          if (!raw.startsWith("data:")) continue;
          try {
            const evt = JSON.parse(raw.slice(5).trim());
            const now = Date.now();
            switch (evt.type) {
              case "begin":
                newConvId = evt.conversation_id;
                setPhase("thinking");
                break;
              case "round":
                // 新一轮 LLM 调用：清掉上一轮的 streamingText（已落到历史）
                // reasoning 也清，方便看本轮思考
                if (evt.round > 1) {
                  textAcc = "";
                  reasoningAcc = "";
                  setStreamingText("");
                  setStreamingReasoning("");
                  setPhase("thinking");
                }
                break;
              case "reasoning":
                reasoningAcc += evt.delta;
                setStreamingReasoning(reasoningAcc);
                setPhase("thinking");
                break;
              case "text":
                textAcc += evt.delta;
                setStreamingText(textAcc);
                if (phase !== "writing") setPhase("writing");
                break;
              case "tool_call_request":
                // request 来时往往还没真正执行；只是 LLM 决定要调
                stepsAcc.push({ kind: "tool", name: evt.name, at: now, status: "running" });
                setSteps([...stepsAcc]);
                setPhase("tool_calling");
                break;
              case "tool_call_running":
                // 正式执行；找到最近一个 running 的同名 tool（应该匹配）
                break;
              case "tool_call_done": {
                // 把最近一个 running 的同名 tool 标 done + result_keys
                for (let i = stepsAcc.length - 1; i >= 0; i--) {
                  const s = stepsAcc[i];
                  if (s.kind === "tool" && s.name === evt.name && s.status === "running") {
                    stepsAcc[i] = { ...s, status: "done", resultKeys: evt.result_keys, at: now };
                    break;
                  }
                }
                setSteps([...stepsAcc]);
                break;
              }
              case "error":
                setPhase("error");
                throw new Error(`${evt.code}: ${evt.message}`);
              case "done":
                setPhase("done");
                break;
            }
          } catch (parseErr) {
            console.warn("SSE parse error", parseErr, raw);
          }
        }
      }
      if (newConvId) setActiveId(newConvId);
      // 流结束：稍等让 useEffect 拉完整会话，再清流式态
      setTimeout(() => {
        setStreamingText("");
        setStreamingReasoning("");
        setSteps([]);
        setPhase("connecting");
      }, 300);
    } catch (e) {
      setPhase("error");
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full gap-4">
      {/* 左侧会话列表 */}
      <aside className="flex w-56 shrink-0 flex-col gap-2 border-r pr-3">
        <Button size="sm" onClick={() => setActiveId(null)}>
          + 新会话
        </Button>
        <div className="flex-1 overflow-y-auto">
          {convList.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={cn(
                "w-full truncate rounded-md px-2 py-2 text-left text-sm hover:bg-muted",
                activeId === c.id && "bg-muted font-medium",
              )}
            >
              <div className="truncate">{c.title || "未命名"}</div>
              <div className="text-[10px] text-muted-foreground">
                {new Date(c.updated_at).toLocaleString("zh-CN")}
              </div>
            </button>
          ))}
          {convList.length === 0 && (
            <p className="px-2 py-4 text-xs text-muted-foreground">暂无历史会话</p>
          )}
        </div>
      </aside>

      {/* 主对话区：min-h-0 让 flex-1 子项可以收缩，否则会撑出滚动 */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto rounded-md border bg-muted/20 p-4">
          {!conv && !activeId && (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <h2 className="mb-2 text-lg font-semibold text-foreground">稳盈 · 对话参谋</h2>
              <p className="max-w-md text-sm">
                问我「未来 13 周哪几周会紧？」「这周有什么闲钱能投？」「不够的话怎么补最省？」
                <br />
                所有金额来自决策引擎的真实求解，绝不凭空生成。
              </p>
            </div>
          )}
          {conv && (
            <div className="flex flex-col gap-3">
              {conv.messages
                .filter((m) => m.role !== "system")
                .map((m) => (
                  <MessageBubble key={m.id} msg={m} />
                ))}
              {busy && (
                <div className="flex flex-col gap-2">
                  <ThinkingPanel
                    phase={phase}
                    startedAt={stepStartAt}
                    steps={steps}
                    reasoning={streamingReasoning}
                  />
                  {streamingText && (
                    <div className="rounded-lg border bg-background px-4 py-3 text-sm">
                      <Markdown>{streamingText}</Markdown>
                      <span className="inline-block h-3 w-1 animate-pulse bg-primary" />
                    </div>
                  )}
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>

        {error && (
          <Card className="mt-2 border-destructive">
            <CardContent className="py-2 text-sm text-destructive">{error}</CardContent>
          </Card>
        )}

        <div className="mt-3 flex shrink-0 items-center gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="问点什么...（Enter 发送 · Shift+Enter 换行）"
            disabled={busy}
            rows={2}
          />
          <Button
            onClick={send}
            disabled={busy || !input.trim()}
            className="h-[3.75rem] shrink-0 px-5"
          >
            {busy ? "..." : "发送"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
          {msg.content}
        </div>
      </div>
    );
  }
  if (msg.role === "tool") {
    return (
      <div className="flex justify-start">
        <details className="max-w-[80%] rounded-lg border bg-background px-3 py-2 text-xs">
          <summary className="cursor-pointer">
            <Badge variant="default">工具返回</Badge>
            <span className="ml-2 font-medium">{TOOL_LABEL[msg.tool_name ?? ""] ?? msg.tool_name}</span>
          </summary>
          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
            {JSON.stringify(msg.tool_result, null, 2)}
          </pre>
        </details>
      </div>
    );
  }
  // assistant
  return (
    <div className="flex justify-start">
      <div className="flex max-w-[85%] flex-col gap-1 rounded-lg border bg-background px-4 py-3 text-sm">
        {msg.tool_name && (
          <div className="flex items-center gap-1">
            <Badge variant="primary">调用工具</Badge>
            <span className="text-xs">{TOOL_LABEL[msg.tool_name] ?? msg.tool_name}</span>
            {msg.tool_args && Object.keys(msg.tool_args).length > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {JSON.stringify(msg.tool_args).slice(0, 80)}
              </span>
            )}
          </div>
        )}
        {msg.reasoning_content && (
          <details className="-mx-1 rounded-md border border-dashed border-border/60 bg-muted/30 px-2 py-1 text-[11px]">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              🧠 思考过程 · {msg.reasoning_content.length} 字
            </summary>
            <div className="mt-1.5 max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed text-muted-foreground">
              {msg.reasoning_content}
            </div>
          </details>
        )}
        {msg.content && <Markdown>{msg.content}</Markdown>}
        {msg.model && (
          <div className="mt-1 text-[10px] text-muted-foreground">
            {msg.model}
            {msg.tokens_in && ` · in ${msg.tokens_in}`}
            {msg.tokens_out && ` · out ${msg.tokens_out}`}
          </div>
        )}
      </div>
    </div>
  );
}
