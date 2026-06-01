"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

export function RunForecastButton({ label = "重新预测" }: { label?: string }) {
  const { data: session } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // @ts-expect-error -- extended session
  const role: string = session?.user?.role ?? "viewer";
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const allowed = ["admin", "treasurer", "analyst"].includes(role);

  async function run() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
      const res = await fetch(`${apiBase}/api/v1/forecast/run`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: "{}",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
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
        {busy ? "预测中..." : label}
      </Button>
      {err && <p className="text-xs text-destructive">{err}</p>}
    </div>
  );
}
