"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

type Summary = {
  ok: boolean;
  imported: Record<string, number>;
  skipped: Record<string, number>;
  issues: { severity: string; table: string; row: number | null; message: string }[];
};

/**
 * 通用适配器调度抽屉：
 * - csv_directory：填路径（容器内的 seed 目录，如 /app/seeds/demo_company）
 * - excel_workbook：上传 .xlsx 文件
 * - 其他自定义 adapter：填 JSON kwargs
 */
export function AdapterImportDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [adapters, setAdapters] = useState<string[]>([]);
  const [picked, setPicked] = useState<string>("csv_directory");
  const [path, setPath] = useState<string>("/app/seeds/demo_company");
  const [rawKwargs, setRawKwargs] = useState<string>("{}");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Summary | null>(null);

  useEffect(() => {
    if (!token || !open) return;
    fetch(`${API}/api/v1/data/adapters`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setAdapters)
      .catch(() => {});
  }, [token, open]);

  function reset() {
    setError(null);
    setResult(null);
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function run() {
    if (!token) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      // Excel 上传走专用端点（避免容器内路径问题）
      if (picked === "excel_workbook" && file) {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(`${API}/api/v1/data/upload-excel`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: r.statusText }));
          throw new Error(err.detail || `HTTP ${r.status}`);
        }
        setResult(await r.json());
        router.refresh();
        return;
      }

      // 其他 adapter：调通用入口
      let kwargs: Record<string, unknown> = {};
      if (picked === "csv_directory") {
        kwargs = { path };
      } else {
        try {
          kwargs = JSON.parse(rawKwargs);
        } catch {
          throw new Error("kwargs JSON 解析失败");
        }
      }
      const r = await fetch(`${API}/api/v1/data/import-from-adapter`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ adapter: picked, kwargs }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      setResult(await r.json());
      router.refresh();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  const errCount = result?.issues.filter((i) => i.severity === "error").length ?? 0;
  const warnCount = result?.issues.filter((i) => i.severity === "warning").length ?? 0;

  return (
    <Drawer
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="数据源适配器"
      width="w-[40rem]"
    >
      <div className="flex flex-col gap-4">
        <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
          <p className="mb-1 font-medium text-foreground">用途</p>
          <p>
            从异构数据源（CSV 目录 / Excel / ERP / 银企）拉取数据，统一映射成稳盈
            Canonical 模型后落库。客户 IT 实现一个 <code className="rounded bg-background px-1">SourceAdapter</code>
            子类，本入口立即可用。详见{" "}
            <a
              href="/doc/适配器接入指南.md"
              target="_blank"
              rel="noopener"
              className="text-primary underline"
            >
              适配器接入指南
            </a>
            。
          </p>
        </div>

        {/* 选 adapter */}
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-muted-foreground">选择 adapter</span>
          <select
            value={picked}
            onChange={(e) => {
              setPicked(e.target.value);
              reset();
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          >
            {adapters.length === 0 ? (
              <option>加载中...</option>
            ) : (
              adapters.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))
            )}
          </select>
        </label>

        {/* 参数 */}
        {picked === "csv_directory" && (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">
              CSV 目录路径（容器内绝对路径）
            </span>
            <Input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/app/seeds/demo_company"
            />
            <span className="text-[10px] text-muted-foreground">
              目录下需有：entities.csv / accounts.csv / balances.csv / cashflows.csv / instruments.csv / credit_lines.csv / reserve_rules.csv
            </span>
          </label>
        )}

        {picked === "excel_workbook" && (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">上传 Excel 工作簿（.xlsx）</span>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
            />
            <span className="text-[10px] text-muted-foreground">
              工作簿需有 7 个 sheet：entities / accounts / balances / cashflows / instruments / credit_lines / reserve_rules
            </span>
            {file && (
              <span className="text-xs text-muted-foreground">
                已选：<span className="font-mono">{file.name}</span> · {(file.size / 1024).toFixed(1)} KB
              </span>
            )}
          </label>
        )}

        {picked !== "csv_directory" && picked !== "excel_workbook" && (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted-foreground">kwargs (JSON)</span>
            <textarea
              value={rawKwargs}
              onChange={(e) => setRawKwargs(e.target.value)}
              rows={6}
              className="rounded-md border border-input bg-background p-2 font-mono text-xs"
              placeholder='{"connection_str": "...", "from_date": "2026-06-01"}'
            />
            <span className="text-[10px] text-muted-foreground">
              敏感字段（password / api_key / token / connection_*）入库时自动脱敏
            </span>
          </label>
        )}

        <div className="border-t pt-3">
          <Button
            onClick={run}
            disabled={
              busy ||
              (picked === "excel_workbook" && !file) ||
              (picked === "csv_directory" && !path)
            }
            className="w-full"
          >
            {busy ? "导入中..." : "执行导入"}
          </Button>
        </div>

        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {result && (
          <div className="flex flex-col gap-2 border-t pt-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={result.ok ? "success" : "destructive"}>
                {result.ok ? "成功" : "有错误"}
              </Badge>
              {errCount > 0 && <Badge variant="destructive">{errCount} error</Badge>}
              {warnCount > 0 && <Badge variant="warning">{warnCount} warn</Badge>}
            </div>

            <details className="rounded-md border bg-muted/20 p-2 text-xs" open>
              <summary className="cursor-pointer text-muted-foreground">
                新增 / 已存在
              </summary>
              <div className="mt-1.5 grid grid-cols-2 gap-x-3 font-mono">
                <div>
                  <div className="mb-0.5 font-medium text-foreground">新增</div>
                  {Object.entries(result.imported).length === 0 && (
                    <div className="text-[10px] text-muted-foreground">（无）</div>
                  )}
                  {Object.entries(result.imported).map(([t, n]) => (
                    <div key={t}>
                      {t}: +{n}
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-0.5 font-medium text-foreground">已存在</div>
                  {Object.entries(result.skipped).length === 0 && (
                    <div className="text-[10px] text-muted-foreground">（无）</div>
                  )}
                  {Object.entries(result.skipped).map(([t, n]) => (
                    <div key={t}>
                      {t}: {n}
                    </div>
                  ))}
                </div>
              </div>
            </details>

            {result.issues.length > 0 && (
              <details className="rounded-md border border-warning/40 bg-warning/5 p-2 text-xs">
                <summary className="cursor-pointer font-medium">
                  问题清单（{result.issues.length}）
                </summary>
                <ul className="mt-1.5 ml-4 list-disc space-y-1">
                  {result.issues.slice(0, 30).map((i, idx) => (
                    <li
                      key={idx}
                      className={
                        i.severity === "error" ? "text-destructive" : "text-warning"
                      }
                    >
                      <span className="font-mono text-[10px]">
                        [{i.table}] row {i.row ?? "?"}
                      </span>{" "}
                      {i.message}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>
    </Drawer>
  );
}
