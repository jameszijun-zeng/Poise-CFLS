"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

type LockRow = {
  week: number;
  amount: string;
};

export function WhatIfDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [locks, setLocks] = useState<LockRow[]>([{ week: 3, amount: "80000000" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  function addLock() {
    setLocks([...locks, { week: 1, amount: "0" }]);
  }
  function rmLock(i: number) {
    setLocks(locks.filter((_, idx) => idx !== i));
  }
  function update(i: number, patch: Partial<LockRow>) {
    setLocks(locks.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  }

  async function runSolve() {
    if (!token) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    const t0 = performance.now();
    try {
      const lockMap = locks.reduce<Record<string, number>>((acc, l) => {
        const amt = Number(l.amount);
        if (l.week >= 1 && l.week <= 13 && amt > 0) acc[String(l.week)] = amt;
        return acc;
      }, {});

      const res = await fetch(`${API}/api/v1/plans/build-and-solve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ locks: lockMap }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      const dt = Math.round(performance.now() - t0);
      const candidates = data.candidates as Array<{
        risk_knob: string;
        expected_net_income: string | null;
        gap_warning: boolean;
      }>;
      const summary = candidates
        .map(
          (c) =>
            `${c.risk_knob}: ¥${Number(c.expected_net_income ?? 0).toLocaleString()}${c.gap_warning ? " ⚠" : ""}`,
        )
        .join("  |  ");
      setStatus(`完成 (${dt} ms) · ${summary}`);
      router.refresh();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="what-if 沙盘" width="w-[32rem]">
      <div className="flex flex-col gap-4">
        <div>
          <h3 className="mb-1 text-sm font-semibold">资金锁定</h3>
          <p className="text-xs text-muted-foreground">
            在指定周次"钉"住一笔资金（不可被投资 / 不可被授信替代），强制 MILP 在 MinCash 之上额外保留。
            常用于：「W3 一定要付的 80M 并购款」「W6 一定要留 30M 备用」。
          </p>
        </div>

        <div className="flex flex-col gap-2 rounded-md border p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <span className="w-16">周次 (1-13)</span>
            <span className="flex-1">金额 (¥)</span>
            <span className="w-8" />
          </div>
          {locks.map((l, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                type="number"
                min={1}
                max={13}
                value={l.week}
                onChange={(e) => update(i, { week: Number(e.target.value) })}
                className="w-16"
              />
              <Input
                type="number"
                min={0}
                step={1000000}
                value={l.amount}
                onChange={(e) => update(i, { amount: e.target.value })}
                className="flex-1"
              />
              <button
                onClick={() => rmLock(i)}
                className="h-8 w-8 rounded-md text-muted-foreground hover:bg-muted"
                title="删除"
              >
                ✕
              </button>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={addLock}>
            + 增加一行
          </Button>
        </div>

        {/* 预设场景 */}
        <div>
          <h3 className="mb-1 text-sm font-semibold">快捷场景</h3>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setLocks([{ week: 3, amount: "80000000" }])}
              className={cn("rounded-md border px-2 py-1 text-xs hover:bg-muted")}
            >
              并购款剧情（W3 锁 ¥80M）
            </button>
            <button
              onClick={() => setLocks([{ week: 11, amount: "30000000" }])}
              className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
            >
              月中工资周（W11 锁 ¥30M）
            </button>
            <button
              onClick={() => setLocks([])}
              className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
            >
              清空（无约束）
            </button>
          </div>
        </div>

        <div className="border-t pt-3">
          <Button onClick={runSolve} disabled={busy} className="w-full">
            {busy ? "求解中..." : "应用锁定 + 重算三档"}
          </Button>
          {status && (
            <div className="mt-2 rounded-md bg-success/10 p-2 text-xs text-success">
              <Badge variant="success" className="mr-2">
                完成
              </Badge>
              {status}
            </div>
          )}
          {error && (
            <div className="mt-2 rounded-md bg-destructive/10 p-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>

        <div className="text-xs text-muted-foreground">
          <p className="mb-1 font-medium">说明</p>
          <p>
            "资金锁定"会作为硬约束注入 MILP：每周末可用现金 B[t] ≥ MinCash[t] × 风险乘子 + 锁定金额。
            若锁定过严会导致不可行，自动走 slack 诊断路径，结果会显示在三档卡片的「缺口预警」标签上。
          </p>
        </div>
      </div>
    </Drawer>
  );
}
