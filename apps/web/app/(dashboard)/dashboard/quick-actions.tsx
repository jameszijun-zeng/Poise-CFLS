"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export function QuickActions() {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;
  // @ts-expect-error
  const role: string = session?.user?.role ?? "viewer";

  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const allowed = ["admin", "treasurer", "analyst"].includes(role);

  async function runForecast() {
    if (!token) return;
    setBusy("forecast");
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/v1/forecast/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: "{}",
      });
      if (!r.ok) throw new Error(await r.text());
      setMsg("✓ 预测已生成");
      router.refresh();
    } catch (e) {
      setMsg(`✗ ${e}`);
    } finally {
      setBusy(null);
    }
  }

  async function runSolve() {
    if (!token) return;
    setBusy("solve");
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/v1/plans/build-and-solve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: "{}",
      });
      if (!r.ok) throw new Error(await r.text());
      setMsg("✓ 三档方案已生成");
      router.refresh();
    } catch (e) {
      setMsg(`✗ ${e}`);
    } finally {
      setBusy(null);
    }
  }

  if (!allowed) {
    return (
      <p className="text-xs text-muted-foreground">
        只读角色暂无快捷操作权限（仅 admin / treasurer / analyst）
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" onClick={runForecast} disabled={busy !== null}>
        {busy === "forecast" ? "..." : "🔄 重新预测"}
      </Button>
      <Button size="sm" variant="outline" onClick={runSolve} disabled={busy !== null}>
        {busy === "solve" ? "..." : "🧮 求解三档"}
      </Button>
      <Button size="sm" variant="outline" onClick={() => router.push("/chat")}>
        💬 对话参谋
      </Button>
      <Button size="sm" variant="ghost" onClick={() => router.push("/forecast")}>
        13 周看板 →
      </Button>
      <Button size="sm" variant="ghost" onClick={() => router.push("/plans")}>
        方案对比 →
      </Button>
      {msg && (
        <span
          className={
            msg.startsWith("✓")
              ? "ml-2 text-xs text-success"
              : "ml-2 text-xs text-destructive"
          }
        >
          {msg}
        </span>
      )}
    </div>
  );
}
