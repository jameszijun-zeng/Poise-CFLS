# 稳盈 / Poise · CSV 数据契约

> 把企业真实数据导入稳盈所需的 7 张 CSV 字段定义。
> 所有 CSV 第 1 行为 header，UTF-8 编码，逗号分隔。
> 金额单位：CNY 元（不带千分符，可带小数点）。
> 日期格式：YYYY-MM-DD。
>
> 导入命令：`make seed` 或前端「数据录入页」→「一键导入 demo_company」

---

## 1. entities.csv（法人主体）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| code | string(50) | ✓ | 主体编码，全局唯一 |
| name | string(200) | ✓ | 主体全称 |
| base_currency | string(3) | | 本币，默认 CNY |

```csv
code,name,base_currency
DEMO,稳盈示范实业有限公司,CNY
```

---

## 2. accounts.csv（银行账户）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| entity_code | string(50) | ✓ | 关联 entities.code |
| code | string(50) | ✓ | 账户编码（主体内唯一） |
| name | string(120) | ✓ | 账户名称 |
| bank_name | string(120) | | 开户行 |
| account_number | string(80) | | 账号（建议脱敏） |
| currency | string(3) | | 币种，默认 CNY |
| account_type | enum | | basic / general / special，默认 basic |

```csv
entity_code,code,name,bank_name,account_number,currency,account_type
DEMO,ACC-BASIC,基本户,中国工商银行,6222********0001,CNY,basic
```

---

## 3. balances.csv（期初余额快照）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| entity_code | string | ✓ | |
| account_code | string | ✓ | 关联 accounts.code |
| as_of_date | date | ✓ | 快照日期 |
| balance | decimal | ✓ | 账面余额 |
| available_balance | decimal | ✓ | 可用余额 |
| restricted_balance | decimal | | 受限余额，默认 0 |
| currency | string(3) | | 默认 CNY |
| source | enum | | eod / real_time，默认 eod |

```csv
entity_code,account_code,as_of_date,balance,available_balance,restricted_balance,currency,source
DEMO,ACC-BASIC,2026-05-30,100000000.00,100000000.00,0.00,CNY,eod
```

---

## 4. cashflows.csv（现金流项 —— 预测的原子）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| entity_code | string | ✓ | |
| account_code | string | | 可选关联 accounts.code |
| direction | enum | ✓ | inflow / outflow |
| category | enum | ✓ | sales_collection / purchase_payment / payroll / tax / interest / principal_repay / rent / other |
| source_type | enum | ✓ | contract / ar / ap / order / schedule / statistical |
| expected_date | date | ✓ | 预期发生日 |
| week_t | int | | 1-13；缺失时按 as_of_date 自动推导 |
| amount | decimal | ✓ | 必须为正数 |
| currency | string(3) | | 默认 CNY |
| certainty_layer | enum | ✓ | deterministic / pattern / uncertain |
| counterparty | string(200) | | 对手方（客户/供应商） |
| notes | text | | 备注 |

**分层建议**：
- `deterministic` (W1–4)：合同到期、AR/AP 已确认、薪酬/税费/利息日程
- `pattern` (W5–8)：账龄统计、季节性回款节奏
- `uncertain` (W9–13)：订单预测、业务驱动；区间默认 ±20%

```csv
entity_code,account_code,direction,category,source_type,expected_date,week_t,amount,currency,certainty_layer,counterparty,notes
DEMO,ACC-COLLECT,inflow,sales_collection,ar,2026-06-03,1,50000000.00,CNY,deterministic,合并AR-多客户,W1销售回款
DEMO,ACC-BASIC,outflow,other,contract,2026-06-19,3,80000000.00,CNY,deterministic,目标公司股权方,W3并购股权款支付
```

---

## 5. instruments.csv（投融资品种主数据）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| entity_code | string | ✓ | |
| code | string(50) | ✓ | 品种编码（主体内唯一） |
| name | string(200) | ✓ | 品种名称 |
| kind | enum | ✓ | invest / finance |
| liquidity_tier | enum | * | 仅 invest 必填：cash / stable / yield |
| rate_annual_pct | decimal | ✓ | 年化百分比（如 2.30 表示 2.30%） |
| tenor_options_weeks | string | ✓ | 多个期限用 \| 分隔，单位周；如 `1\|2\|4\|12`；0 表示 T+0/活期 |
| min_amount | decimal | | 起投金额，默认 0 |
| max_amount | decimal | | 单笔上限，缺省则取 entity 期初余额 + 正净 CF |
| redeemable | bool | | True / False |
| redeem_cost_pct | decimal | | 提前赎回成本百分比，默认 0 |
| counterparty | string(120) | | 对手方银行 |
| whitelisted | bool | | False 则不进入 MILP 选项 |
| finance_priority | int | * | 仅 finance 必填：成本升序优先级（1 最低成本） |
| currency | string(3) | | 默认 CNY |
| notes | text | | |

```csv
entity_code,code,name,kind,liquidity_tier,rate_annual_pct,tenor_options_weeks,min_amount,max_amount,redeemable,redeem_cost_pct,counterparty,whitelisted,finance_priority,currency,notes
DEMO,MMF-A,工银货币基金,invest,cash,2.30,0,1000000,,True,0.00,中国工商银行,True,,CNY,T+0/T+1赎回
DEMO,LOAN-WC,流动资金贷款,finance,,4.35,0,1000000,,False,0.00,中国工商银行,True,1,CNY,授信下随借随还
```

---

## 6. credit_lines.csv（授信额度）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| entity_code | string | ✓ | |
| instrument_code | string | | 关联 instruments.code（kind=finance） |
| bank_name | string(120) | ✓ | |
| code | string(50) | ✓ | 授信编号 |
| limit_amount | decimal | ✓ | 总额度 |
| used_amount | decimal | | 已用，默认 0；必须 ≤ limit_amount |
| rate_annual_pct | decimal | ✓ | 利率年化 % |
| expires_at | date | | 到期日 |
| notes | text | | |

```csv
entity_code,instrument_code,bank_name,code,limit_amount,used_amount,rate_annual_pct,expires_at,notes
DEMO,LOAN-WC,中国工商银行,WC-ICBC-001,80000000.00,0.00,4.35,2027-05-30,流贷主授信
```

---

## 7. reserve_rules.csv（备付金规则）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| entity_code | string | ✓ | 一个主体一条 |
| rule_type | enum | ✓ | fixed / rolling_coverage |
| fixed_value | decimal | * | rule_type=fixed 时必填 |
| rolling_weeks | int | * | rule_type=rolling_coverage 时必填，覆盖未来 N 周刚性支出 |
| notes | text | | |

**刚性支出类别**：payroll / tax / interest / principal_repay / rent
（purchase_payment 和 other 视为可弹性，不纳入 rolling_coverage）

```csv
entity_code,rule_type,fixed_value,rolling_weeks,notes
DEMO,rolling_coverage,,4,最低备付=未来4周刚性支出之和
```

---

## 数据质量门规则（拒绝入库的硬条件）

1. **必填字段缺失** → error，拒绝该行
2. **枚举值非法**（如 direction='sideways'） → error
3. **金额为负或零** → error（amount > 0 才入库）
4. **币种不支持**（MVP 只 CNY） → error
5. **used_amount > limit_amount** → error
6. **invest 缺 liquidity_tier** / **finance 设了 liquidity_tier** → error / warning
7. **金额异常大**（> ¥10 亿）→ warning，仍入库
8. **未知 entity_code / account_code** → error

详细规则见 `apps/api/poise/data_integration/quality_gate.py`。

---

## 导入顺序（重要）

```
entities → accounts → instruments → credit_lines → reserve_rules → balances → cashflows
```

外键关系决定了顺序。`make seed` 或 API `POST /api/v1/data/import-demo` 已按此顺序串行。

---

## 自定义企业数据

把 `apps/api/seeds/demo_company/` 整目录复制为 `apps/api/seeds/<your_company>/`，按上面契约改写 CSV，然后修改 `importers.py` 中 `DEFAULT_SEED_DIR` 或调用 `import_demo_company(seed_dir=Path(...))` 显式指定。

未来支持的扩展：
- Web 上传 CSV（Phase 1 占位已有）
- ERP 适配器（SAP / Oracle / 用友 / 金蝶 → 标准数据契约）
- 银企直连（实时余额 + 流水）
