"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

type ImportSummary = {
  imported: Record<string, number>;
  skipped: Record<string, number>;
  issues: Array<{ severity: string; table: string; message: string }>;
  ok: boolean;
};

export function ImportDemoButton() {
  const { data: session } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  // @ts-expect-error -- extended session
  const role: string = session?.user?.role ?? "viewer";
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const allowed = role === "admin" || role === "treasurer" || role === "analyst";

  async function trigger() {
    if (!token) {
      setError("未登录");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
      const res = await fetch(`${apiBase}/api/v1/data/import-demo`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = (await res.json()) as ImportSummary;
      setResult(data);
      router.refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!allowed) {
    return <p className="text-sm text-muted-foreground">需要 admin / treasurer / analyst 权限</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <Button onClick={trigger} disabled={busy}>
        {busy ? "导入中..." : "一键导入 demo_company 种子数据"}
      </Button>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && (
        <div className="rounded-md border bg-success/5 p-3 text-sm">
          <p className="font-medium">导入完成 · ok={String(result.ok)}</p>
          <div className="mt-1 grid grid-cols-2 gap-x-4 text-xs text-muted-foreground">
            <div>
              <div className="font-medium text-foreground">新增</div>
              {Object.entries(result.imported).map(([t, n]) => (
                <div key={t}>
                  {t}: +{n}
                </div>
              ))}
            </div>
            <div>
              <div className="font-medium text-foreground">跳过</div>
              {Object.entries(result.skipped).map(([t, n]) => (
                <div key={t}>
                  {t}: {n}
                </div>
              ))}
            </div>
          </div>
          {result.issues.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-warning">
                issues: {result.issues.length}
              </summary>
              <ul className="mt-1 list-disc pl-4 text-xs">
                {result.issues.slice(0, 10).map((iss, i) => (
                  <li key={i}>
                    [{iss.severity}] {iss.table}: {iss.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
