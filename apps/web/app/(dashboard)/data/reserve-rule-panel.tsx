"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

type Rule = {
  id: string;
  rule_type: "fixed" | "rolling_coverage";
  fixed_value: string | null;
  rolling_weeks: number | null;
};

export function ReserveRulePanel() {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;
  const [rule, setRule] = useState<Rule | null>(null);
  const [type, setType] = useState<"fixed" | "rolling_coverage">("rolling_coverage");
  const [weeks, setWeeks] = useState("4");
  const [fixedVal, setFixedVal] = useState("50000000");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    const r = await fetch(`${API}/api/v1/data/reserve-rules`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) return;
    const data: Rule[] = await r.json();
    if (data[0]) {
      setRule(data[0]);
      setType(data[0].rule_type);
      setWeeks(String(data[0].rolling_weeks ?? 4));
      setFixedVal(data[0].fixed_value ?? "50000000");
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    if (!token) return;
    setBusy(true);
    setMsg(null);
    try {
      const body: Record<string, unknown> = {
        rule_type: type,
        notes,
      };
      if (type === "fixed") body.fixed_value = fixedVal;
      else body.rolling_weeks = Number(weeks);

      const r = await fetch(`${API}/api/v1/data/reserve-rules`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      await load();
      router.refresh();
      setMsg("✓ 已保存");
      setTimeout(() => setMsg(null), 2000);
    } catch (e) {
      setMsg(`✗ ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">备付金规则</p>
          <p className="mt-1">
            决定 MILP 求解时的最低备付 MinCash[t]：每周末可用现金 ≥ MinCash[t]。
            <br />
            <code className="rounded bg-background px-1">rolling_coverage</code>=未来 N 周刚性支出之和；
            <code className="rounded bg-background px-1">fixed</code>=每周常数值。
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-xs text-muted-foreground">规则类型</label>
          <div className="flex gap-2">
            <label className="flex flex-1 cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted">
              <input
                type="radio"
                checked={type === "rolling_coverage"}
                onChange={() => setType("rolling_coverage")}
              />
              <span>滚动覆盖（rolling_coverage）</span>
            </label>
            <label className="flex flex-1 cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted">
              <input
                type="radio"
                checked={type === "fixed"}
                onChange={() => setType("fixed")}
              />
              <span>固定值（fixed）</span>
            </label>
          </div>
        </div>

        {type === "rolling_coverage" ? (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">滚动周数 N（覆盖未来 N 周刚性支出）</span>
            <Input
              type="number"
              min={1}
              max={13}
              value={weeks}
              onChange={(e) => setWeeks(e.target.value)}
            />
            <span className="text-[10px] text-muted-foreground">
              刚性支出 = payroll / tax / interest / principal_repay / rent
            </span>
          </label>
        ) : (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">固定 MinCash ¥</span>
            <Input
              type="number"
              min={0}
              step={1000000}
              value={fixedVal}
              onChange={(e) => setFixedVal(e.target.value)}
            />
          </label>
        )}

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-muted-foreground">备注</span>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="可选" />
        </label>

        <div className="flex items-center justify-between border-t pt-3">
          <span className="text-xs text-muted-foreground">
            {rule ? `当前规则 id: ${rule.id.slice(0, 8)}...` : "尚未配置"}
          </span>
          <div className="flex items-center gap-3">
            {msg && (
              <span
                className={msg.startsWith("✓") ? "text-xs text-success" : "text-xs text-destructive"}
              >
                {msg}
              </span>
            )}
            <Button onClick={save} disabled={busy} size="sm">
              {busy ? "..." : rule ? "更新" : "创建"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
