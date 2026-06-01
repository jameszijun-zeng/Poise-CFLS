import { getServerSession } from "next-auth";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DataTable, fmtMoney, fmtPct } from "@/components/data-table";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

import { ImportDemoButton } from "./import-button";

type Account = {
  id: string;
  code: string;
  name: string;
  bank_name: string | null;
  currency: string;
  account_type: string;
};

type Balance = {
  id: number;
  account_id: string;
  as_of_date: string;
  balance: string;
  available_balance: string;
  restricted_balance: string;
  currency: string;
};

type CashFlow = {
  id: string;
  direction: "inflow" | "outflow";
  category: string;
  source_type: string;
  expected_date: string;
  week_t: number | null;
  amount: string;
  certainty_layer: "deterministic" | "pattern" | "uncertain";
  counterparty: string | null;
  notes: string | null;
};

type Instrument = {
  id: string;
  code: string;
  name: string;
  kind: "invest" | "finance";
  liquidity_tier: string | null;
  rate: string;
  tenor_options: number[];
  min_amount: string;
  redeemable: boolean;
  counterparty: string | null;
  finance_priority: number | null;
};

type CreditLine = {
  id: string;
  bank_name: string;
  code: string;
  limit_amount: string;
  used_amount: string;
  available_amount: string;
  rate: string;
};

type ReserveRule = {
  id: string;
  rule_type: string;
  fixed_value: string | null;
  rolling_weeks: number | null;
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

const TIER_LABEL: Record<string, string> = {
  cash: "活钱层",
  stable: "稳健层",
  yield: "增益层",
};

export default async function DataPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error -- extended session
  const token: string | undefined = session?.accessToken;

  const [accounts, balances, cashflows, instruments, creditLines, reserveRules] =
    await Promise.all([
      apiFetch<Account[]>("/api/v1/data/accounts", { token }).catch(() => []),
      apiFetch<Balance[]>("/api/v1/data/balances", { token }).catch(() => []),
      apiFetch<CashFlow[]>("/api/v1/data/cashflows", { token }).catch(() => []),
      apiFetch<Instrument[]>("/api/v1/data/instruments", { token }).catch(() => []),
      apiFetch<CreditLine[]>("/api/v1/data/credit-lines", { token }).catch(() => []),
      apiFetch<ReserveRule[]>("/api/v1/data/reserve-rules", { token }).catch(() => []),
    ]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">数据录入</h1>
          <p className="text-sm text-muted-foreground">
            Phase 1 · 浏览已入库的现金流项、品种、授信、备付规则与余额。
            CSV 上传与单表编辑 UI 将在后续 Phase 1 增量补齐。
          </p>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>种子数据导入</CardTitle>
          <CardDescription>幂等 —— 已存在记录会被 upsert</CardDescription>
        </CardHeader>
        <CardContent>
          <ImportDemoButton />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>银行账户（{accounts.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={accounts}
            columns={[
              { header: "Code", cell: (r) => r.code },
              { header: "名称", cell: (r) => r.name },
              { header: "开户行", cell: (r) => r.bank_name ?? "-" },
              { header: "类型", cell: (r) => r.account_type, align: "center" },
              { header: "币种", cell: (r) => r.currency, align: "center" },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>期初余额快照（{balances.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={balances}
            columns={[
              { header: "账户 ID", cell: (r) => r.account_id.slice(0, 8) + "..." },
              { header: "日期", cell: (r) => r.as_of_date },
              { header: "余额", cell: (r) => fmtMoney(r.balance), align: "right" },
              { header: "可用", cell: (r) => fmtMoney(r.available_balance), align: "right" },
              { header: "受限", cell: (r) => fmtMoney(r.restricted_balance), align: "right" },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>13 周现金流项（{cashflows.length}）</CardTitle>
          <CardDescription>分层：确定 / 规律 / 不确定</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={cashflows}
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
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>投融资品种白名单（{instruments.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={instruments}
            columns={[
              { header: "Code", cell: (r) => r.code },
              { header: "名称", cell: (r) => r.name },
              {
                header: "方向",
                cell: (r) => (
                  <Badge variant={r.kind === "invest" ? "primary" : "warning"}>
                    {r.kind === "invest" ? "投资" : "融资"}
                  </Badge>
                ),
                align: "center",
              },
              {
                header: "分层 / 优先",
                cell: (r) =>
                  r.kind === "invest"
                    ? TIER_LABEL[r.liquidity_tier ?? ""] ?? "-"
                    : `优先级 ${r.finance_priority ?? "-"}`,
              },
              { header: "年化", cell: (r) => fmtPct(r.rate), align: "right" },
              { header: "期限(周)", cell: (r) => r.tenor_options.join(",") || "-", align: "center" },
              {
                header: "起投",
                cell: (r) => (Number(r.min_amount) > 0 ? fmtMoney(r.min_amount) : "-"),
                align: "right",
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>授信额度（{creditLines.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={creditLines}
            columns={[
              { header: "授信编号", cell: (r) => r.code },
              { header: "银行", cell: (r) => r.bank_name },
              { header: "额度", cell: (r) => fmtMoney(r.limit_amount), align: "right" },
              { header: "已用", cell: (r) => fmtMoney(r.used_amount), align: "right" },
              {
                header: "可用",
                cell: (r) => (
                  <span className="font-medium text-success">{fmtMoney(r.available_amount)}</span>
                ),
                align: "right",
              },
              { header: "成本", cell: (r) => fmtPct(r.rate), align: "right" },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>备付金规则</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={reserveRules}
            columns={[
              { header: "规则类型", cell: (r) => r.rule_type },
              {
                header: "定值",
                cell: (r) => (r.fixed_value ? fmtMoney(r.fixed_value) : "-"),
                align: "right",
              },
              {
                header: "滚动周数",
                cell: (r) => (r.rolling_weeks != null ? `${r.rolling_weeks} 周` : "-"),
                align: "center",
              },
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
