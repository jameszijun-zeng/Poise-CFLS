"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, fmtMoney } from "@/components/data-table";

import { CashFlowFormDrawer, type CashFlowDraft } from "./cashflow-form";
import { CsvUploadDrawer } from "./csv-upload-drawer";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

type CashFlow = {
  id: string;
  account_id: string | null;
  direction: "inflow" | "outflow";
  category: string;
  source_type: string;
  expected_date: string;
  week_t: number | null;
  amount: string;
  currency: string;
  certainty_layer: "deterministic" | "pattern" | "uncertain";
  counterparty: string | null;
  notes: string | null;
};

const CATEGORY_LABEL: Record<string, string> = {
  sales_collection: "销售回款",
  purchase_payment: "采购付款",
  payroll: "薪酬",
  tax: "税费",
  interest: "利息",
  principal_repay: "还本",
  rent: "租金",
  other: "其他",
};

export function CashFlowPanel() {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [items, setItems] = useState<CashFlow[]>([]);
  const [editing, setEditing] = useState<CashFlowDraft | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showCsv, setShowCsv] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    const r = await fetch(`${API}/api/v1/data/cashflows`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (r.ok) setItems(await r.json());
  }, [token]);

  useEffect(() => {
    load();
  }, [load, showForm, showCsv]);

  async function del(id: string) {
    if (!token) return;
    if (!confirm("确认删除这条现金流项？此操作不可撤销（会留 AuditLog）")) return;
    setBusy(true);
    try {
      await fetch(`${API}/api/v1/data/cashflows/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      await load();
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  function openCreate() {
    setEditing(null);
    setShowForm(true);
  }

  function openEdit(cf: CashFlow) {
    setEditing({
      id: cf.id,
      account_id: cf.account_id,
      direction: cf.direction,
      category: cf.category,
      source_type: cf.source_type,
      expected_date: cf.expected_date,
      week_t: cf.week_t,
      amount: cf.amount,
      currency: cf.currency,
      certainty_layer: cf.certainty_layer,
      counterparty: cf.counterparty,
      notes: cf.notes,
    });
    setShowForm(true);
  }

  // 简要统计
  const inflowTotal = items.filter((i) => i.direction === "inflow").reduce((s, i) => s + Number(i.amount), 0);
  const outflowTotal = items.filter((i) => i.direction === "outflow").reduce((s, i) => s + Number(i.amount), 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-3 text-xs">
          <span>共 <b>{items.length}</b> 条</span>
          <span>·</span>
          <span className="text-success">收 {fmtMoney(inflowTotal)}</span>
          <span>·</span>
          <span className="text-warning">付 {fmtMoney(outflowTotal)}</span>
          <span>·</span>
          <span className={inflowTotal - outflowTotal >= 0 ? "text-success" : "text-destructive"}>
            净 {fmtMoney(inflowTotal - outflowTotal)}
          </span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowCsv(true)}>
            📤 CSV 上传
          </Button>
          <Button size="sm" onClick={openCreate}>
            + 新增
          </Button>
        </div>
      </div>

      <DataTable
        rows={items}
        columns={[
          { header: "W", cell: (r) => r.week_t ?? "-", align: "center", width: "3rem" },
          { header: "日期", cell: (r) => r.expected_date },
          {
            header: "方向",
            cell: (r) => (
              <Badge variant={r.direction === "inflow" ? "success" : "warning"}>
                {r.direction === "inflow" ? "收" : "付"}
              </Badge>
            ),
            align: "center",
          },
          { header: "类别", cell: (r) => CATEGORY_LABEL[r.category] ?? r.category },
          { header: "金额", cell: (r) => fmtMoney(r.amount), align: "right" },
          {
            header: "层",
            cell: (r) => (
              <Badge
                variant={
                  r.certainty_layer === "deterministic"
                    ? "primary"
                    : r.certainty_layer === "pattern"
                      ? "default"
                      : "warning"
                }
              >
                {r.certainty_layer === "deterministic"
                  ? "确定"
                  : r.certainty_layer === "pattern"
                    ? "规律"
                    : "不确定"}
              </Badge>
            ),
            align: "center",
          },
          { header: "对手方", cell: (r) => r.counterparty ?? "-" },
          {
            header: "操作",
            cell: (r) => (
              <div className="flex justify-end gap-1">
                <Button size="sm" variant="ghost" onClick={() => openEdit(r)} disabled={busy}>
                  编辑
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => del(r.id)}
                  disabled={busy}
                  className="text-destructive hover:bg-destructive/10"
                >
                  删除
                </Button>
              </div>
            ),
            align: "right",
          },
        ]}
        empty="尚无现金流项 · 点「+ 新增」或「📤 CSV 上传」"
      />

      <CashFlowFormDrawer
        open={showForm}
        onClose={() => setShowForm(false)}
        initial={editing}
      />
      <CsvUploadDrawer
        open={showCsv}
        onClose={() => setShowCsv(false)}
        table="cashflows"
      />
    </div>
  );
}
