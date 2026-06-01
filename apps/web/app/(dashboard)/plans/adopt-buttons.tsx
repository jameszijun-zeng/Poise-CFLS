"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

export function AdoptButtons({ planId, status }: { planId: string; status: string }) {
  const { data: session } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // @ts-expect-error
  const role: string = session?.user?.role ?? "viewer";
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const canAdopt = ["admin", "treasurer"].includes(role);

  async function act(verb: "adopt" | "reject") {
    if (!token) return;
    setBusy(verb);
    setErr(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
      const res = await fetch(`${apiBase}/api/v1/plans/${planId}/${verb}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      router.refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  if (status === "adopted") {
    return <span className="text-sm font-semibold text-success">✓ 已采纳</span>;
  }
  if (status === "rejected") {
    return <span className="text-sm text-muted-foreground">已否决</span>;
  }
  if (!canAdopt) {
    return <span className="text-xs text-muted-foreground">需 treasurer 或 admin 角色</span>;
  }
  return (
    <div className="flex items-center gap-2">
      <Button size="sm" onClick={() => act("adopt")} disabled={busy !== null}>
        {busy === "adopt" ? "..." : "采纳"}
      </Button>
      <Button size="sm" variant="outline" onClick={() => act("reject")} disabled={busy !== null}>
        {busy === "reject" ? "..." : "否决"}
      </Button>
      {err && <span className="text-xs text-destructive">{err}</span>}
    </div>
  );
}
