"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export type CashFlowDraft = {
  id?: string;
  account_id?: string | null;
  direction: "inflow" | "outflow";
  category: string;
  source_type: string;
  expected_date: string;
  week_t?: number | null;
  amount: string;
  currency: string;
  certainty_layer: "deterministic" | "pattern" | "uncertain";
  counterparty?: string | null;
  notes?: string | null;
};

const CATEGORIES = [
  { v: "sales_collection", l: "销售回款" },
  { v: "purchase_payment", l: "采购付款" },
  { v: "payroll", l: "薪酬" },
  { v: "tax", l: "税费" },
  { v: "interest", l: "利息" },
  { v: "principal_repay", l: "还本" },
  { v: "rent", l: "租金" },
  { v: "other", l: "其他" },
];

const SOURCE_TYPES = [
  { v: "contract", l: "合同（已签）" },
  { v: "ar", l: "应收（已开票）" },
  { v: "ap", l: "应付（已开票）" },
  { v: "order", l: "订单" },
  { v: "schedule", l: "日历日程" },
  { v: "statistical", l: "统计估算" },
];

const LAYERS = [
  { v: "deterministic", l: "确定（W1-4）" },
  { v: "pattern", l: "规律（W5-8）" },
  { v: "uncertain", l: "不确定（W9-13）" },
];

const empty: CashFlowDraft = {
  direction: "inflow",
  category: "sales_collection",
  source_type: "ar",
  expected_date: new Date().toISOString().slice(0, 10),
  amount: "1000000",
  currency: "CNY",
  certainty_layer: "deterministic",
  counterparty: "",
  notes: "",
};

type Account = { id: string; code: string; name: string };

export function CashFlowFormDrawer({
  open,
  onClose,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  initial?: CashFlowDraft | null;
}) {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;
  const [form, setForm] = useState<CashFlowDraft>(initial ?? empty);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEdit = !!initial?.id;

  useEffect(() => {
    setForm(initial ?? empty);
    setError(null);
  }, [initial, open]);

  useEffect(() => {
    if (!token || !open) return;
    fetch(`${API}/api/v1/data/accounts`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setAccounts)
      .catch(() => {});
  }, [token, open]);

  async function submit() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const url = isEdit
        ? `${API}/api/v1/data/cashflows/${initial!.id}`
        : `${API}/api/v1/data/cashflows`;
      const body = {
        ...form,
        amount: form.amount,
        week_t: form.week_t || null,
        account_id: form.account_id || null,
        counterparty: form.counterparty || null,
        notes: form.notes || null,
      };
      const r = await fetch(url, {
        method: isEdit ? "PATCH" : "POST",
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
      router.refresh();
      onClose();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={isEdit ? "编辑现金流项" : "新增现金流项"}
      width="w-[34rem]"
    >
      <div className="flex flex-col gap-3">
        {/* 方向 + 类别 一行 */}
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">方向 *</span>
            <select
              value={form.direction}
              onChange={(e) => setForm({ ...form, direction: e.target.value as never })}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="inflow">收 inflow</option>
              <option value="outflow">付 outflow</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">类别 *</span>
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              {CATEGORIES.map((c) => (
                <option key={c.v} value={c.v}>{c.l}（{c.v}）</option>
              ))}
            </select>
          </label>
        </div>

        {/* 数据来源 + 确定性 */}
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">数据来源 *</span>
            <select
              value={form.source_type}
              onChange={(e) => setForm({ ...form, source_type: e.target.value })}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              {SOURCE_TYPES.map((s) => (
                <option key={s.v} value={s.v}>{s.l}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">确定性分层 *</span>
            <select
              value={form.certainty_layer}
              onChange={(e) => setForm({ ...form, certainty_layer: e.target.value as never })}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              {LAYERS.map((l) => (
                <option key={l.v} value={l.v}>{l.l}</option>
              ))}
            </select>
          </label>
        </div>

        {/* 日期 + 周次 + 账户 */}
        <div className="grid grid-cols-3 gap-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">预期发生日 *</span>
            <Input
              type="date"
              value={form.expected_date}
              onChange={(e) => setForm({ ...form, expected_date: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">周次 (1-13)</span>
            <Input
              type="number"
              min={1}
              max={13}
              value={form.week_t ?? ""}
              onChange={(e) => setForm({ ...form, week_t: e.target.value ? Number(e.target.value) : null })}
              placeholder="自动推导"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">账户</span>
            <select
              value={form.account_id ?? ""}
              onChange={(e) => setForm({ ...form, account_id: e.target.value || null })}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="">不指定</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.code} / {a.name}</option>
              ))}
            </select>
          </label>
        </div>

        {/* 金额 + 币种 */}
        <div className="grid grid-cols-3 gap-2">
          <label className="col-span-2 flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">金额 ¥ *（正数）</span>
            <Input
              type="number"
              min={0}
              step={1000}
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">币种</span>
            <select
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="CNY">CNY</option>
            </select>
          </label>
        </div>

        {/* 对手方 */}
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-muted-foreground">对手方（客户 / 供应商）</span>
          <Input
            value={form.counterparty ?? ""}
            onChange={(e) => setForm({ ...form, counterparty: e.target.value })}
            placeholder="如：北辰电气 / 合并 AR-多客户"
          />
        </label>

        {/* 备注 */}
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-muted-foreground">备注</span>
          <Textarea
            value={form.notes ?? ""}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="可选"
            rows={2}
          />
        </label>

        {error && (
          <div className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="mt-2 flex gap-2 border-t pt-3">
          <Button variant="outline" onClick={onClose} disabled={busy} className="flex-1">
            取消
          </Button>
          <Button onClick={submit} disabled={busy} className="flex-1">
            {busy ? "保存中..." : isEdit ? "保存修改" : "新增"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}
