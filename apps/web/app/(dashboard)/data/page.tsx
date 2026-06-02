import { getServerSession } from "next-auth";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fmtMoney, fmtPct } from "@/components/data-table";
import { apiFetch } from "@/lib/api";
import { authOptions } from "@/lib/auth";

import { AdapterImportButton } from "./adapter-import-button";
import { CashFlowPanel } from "./cashflow-panel";
import { ImportDemoButton } from "./import-button";
import { ReadonlyWithCsv } from "./readonly-with-csv";
import { ReserveRulePanel } from "./reserve-rule-panel";

type Account = {
  id: string;
  code: string;
  name: string;
  bank_name: string | null;
  currency: string;
  account_type: string;
  is_active: boolean;
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
  whitelisted: boolean;
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

const TIER_LABEL: Record<string, string> = {
  cash: "活钱层",
  stable: "稳健层",
  yield: "增益层",
};
const ACCT_TYPE_LABEL: Record<string, string> = {
  basic: "基本户",
  general: "一般户",
  special: "专户",
};

export default async function DataPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error -- extended session
  const token: string | undefined = session?.accessToken;

  const [accounts, balances, instruments, creditLines] = await Promise.all([
    apiFetch<Account[]>("/api/v1/data/accounts", { token }).catch(() => []),
    apiFetch<Balance[]>("/api/v1/data/balances", { token }).catch(() => []),
    apiFetch<Instrument[]>("/api/v1/data/instruments", { token }).catch(() => []),
    apiFetch<CreditLine[]>("/api/v1/data/credit-lines", { token }).catch(() => []),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">数据录入</h1>
          <p className="text-sm text-muted-foreground">
            6 张核心表 · 手工增删改 + CSV 批量上传 + 数据质量门校验
          </p>
        </div>
      </header>

      {/* 种子导入 + 适配器入口 */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle>批量数据导入</CardTitle>
              <CardDescription>
                演示环境一键导入 · 真实环境用适配器接入 ERP / 银企 / Excel
              </CardDescription>
            </div>
            <AdapterImportButton />
          </div>
        </CardHeader>
        <CardContent>
          <ImportDemoButton />
        </CardContent>
      </Card>

      {/* 主体：6 表 tab */}
      <Card>
        <CardHeader>
          <CardTitle>核心数据</CardTitle>
          <CardDescription>
            点 tab 切换；现金流支持完整手工 CRUD；其它表通过 CSV 上传批量管理
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="cashflows">
            <TabsList>
              <TabsTrigger value="cashflows">现金流项</TabsTrigger>
              <TabsTrigger value="instruments">投融资品种</TabsTrigger>
              <TabsTrigger value="credit-lines">授信额度</TabsTrigger>
              <TabsTrigger value="reserve-rules">备付规则</TabsTrigger>
              <TabsTrigger value="accounts">银行账户</TabsTrigger>
              <TabsTrigger value="balances">余额快照</TabsTrigger>
            </TabsList>

            <TabsContent value="cashflows">
              <CashFlowPanel />
            </TabsContent>

            <TabsContent value="instruments">
              <ReadonlyWithCsv
                rows={instruments}
                table="instruments"
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
                  {
                    header: "期限(周)",
                    cell: (r) => r.tenor_options.join(",") || "-",
                    align: "center",
                  },
                  {
                    header: "起投",
                    cell: (r) => (Number(r.min_amount) > 0 ? fmtMoney(r.min_amount) : "-"),
                    align: "right",
                  },
                  {
                    header: "白名单",
                    cell: (r) =>
                      r.whitelisted ? (
                        <Badge variant="success">在</Badge>
                      ) : (
                        <Badge variant="default">已下架</Badge>
                      ),
                    align: "center",
                  },
                ]}
              />
            </TabsContent>

            <TabsContent value="credit-lines">
              <ReadonlyWithCsv
                rows={creditLines}
                table="credit_lines"
                columns={[
                  { header: "授信编号", cell: (r) => r.code },
                  { header: "银行", cell: (r) => r.bank_name },
                  { header: "额度", cell: (r) => fmtMoney(r.limit_amount), align: "right" },
                  { header: "已用", cell: (r) => fmtMoney(r.used_amount), align: "right" },
                  {
                    header: "可用",
                    cell: (r) => (
                      <span className="font-medium text-success">
                        {fmtMoney(r.available_amount)}
                      </span>
                    ),
                    align: "right",
                  },
                  { header: "成本", cell: (r) => fmtPct(r.rate), align: "right" },
                ]}
              />
            </TabsContent>

            <TabsContent value="reserve-rules">
              <ReserveRulePanel />
            </TabsContent>

            <TabsContent value="accounts">
              <ReadonlyWithCsv
                rows={accounts}
                table="accounts"
                columns={[
                  { header: "Code", cell: (r) => r.code },
                  { header: "名称", cell: (r) => r.name },
                  { header: "开户行", cell: (r) => r.bank_name ?? "-" },
                  {
                    header: "类型",
                    cell: (r) => ACCT_TYPE_LABEL[r.account_type] ?? r.account_type,
                    align: "center",
                  },
                  { header: "币种", cell: (r) => r.currency, align: "center" },
                  {
                    header: "状态",
                    cell: (r) =>
                      r.is_active ? (
                        <Badge variant="success">激活</Badge>
                      ) : (
                        <Badge variant="default">停用</Badge>
                      ),
                    align: "center",
                  },
                ]}
              />
            </TabsContent>

            <TabsContent value="balances">
              <ReadonlyWithCsv
                rows={balances}
                table="balances"
                columns={[
                  { header: "账户 ID", cell: (r) => r.account_id.slice(0, 8) + "..." },
                  { header: "日期", cell: (r) => r.as_of_date },
                  { header: "余额", cell: (r) => fmtMoney(r.balance), align: "right" },
                  { header: "可用", cell: (r) => fmtMoney(r.available_balance), align: "right" },
                  { header: "受限", cell: (r) => fmtMoney(r.restricted_balance), align: "right" },
                ]}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
