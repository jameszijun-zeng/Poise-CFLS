"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

export function SolveButton({ label = "重新求解（三档 MILP）" }: { label?: string }) {
  const { data: session } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [stat, setStat] = useState<string | null>(null);

  // @ts-expect-error
  const role: string = session?.user?.role ?? "viewer";
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const allowed = ["admin", "treasurer", "analyst"].includes(role);

  async function run() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    setStat(null);
    const t0 = performance.now();
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
      const res = await fetch(`${apiBase}/api/v1/plans/build-and-solve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = await res.json();
      const dt = Math.round(performance.now() - t0);
      setStat(`完成 · ${data.candidates.length} 档 / ${dt} ms`);
      router.refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!allowed) return null;
  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={run} disabled={busy} size="sm">
        {busy ? "求解中..." : label}
      </Button>
      {stat && <p className="text-xs text-success">{stat}</p>}
      {err && <p className="text-xs text-destructive">{err}</p>}
    </div>
  );
}
