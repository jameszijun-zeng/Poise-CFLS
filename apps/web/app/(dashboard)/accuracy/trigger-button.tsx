"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export function TriggerRollingButton() {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const role: string = session?.user?.role ?? "viewer";
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [week, setWeek] = useState(1);

  const allowed = ["admin", "treasurer", "analyst"].includes(role);
  if (!allowed) return null;

  async function trigger() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    setStatus(null);
    const t0 = performance.now();
    try {
      const r = await fetch(`${API}/api/v1/feedback/trigger-rolling`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ target_week: week, rerun_forecast: true }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      const dt = Math.round(performance.now() - t0);
      setStatus(`${data.summary} · 端到端 ${dt} ms`);
      router.refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        <label className="text-xs text-muted-foreground">滚动目标周</label>
        <select
          value={week}
          onChange={(e) => setWeek(Number(e.target.value))}
          className="h-8 rounded-md border border-input bg-background px-2 text-sm"
          disabled={busy}
        >
          {Array.from({ length: 13 }, (_, i) => i + 1).map((w) => (
            <option key={w} value={w}>
              W{w}
            </option>
          ))}
        </select>
        <Button onClick={trigger} disabled={busy} size="sm">
          {busy ? "..." : "手动触发滚动重跑"}
        </Button>
      </div>
      {status && <p className="max-w-md text-right text-xs text-success">{status}</p>}
      {err && <p className="text-xs text-destructive">{err}</p>}
    </div>
  );
}
