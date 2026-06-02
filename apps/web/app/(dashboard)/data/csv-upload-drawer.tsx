"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";

type Issue = {
  severity: "error" | "warning";
  table: string;
  row: number | null;
  field: string | null;
  message: string;
};

type Preview = {
  table: string;
  total_rows: number;
  valid_rows: number;
  sample: Record<string, unknown>[];
  issues: Issue[];
};

const TABLE_LABEL: Record<string, string> = {
  accounts: "账户",
  balances: "余额快照",
  cashflows: "现金流项",
  instruments: "投融资品种",
  credit_lines: "授信额度",
  reserve_rules: "备付规则",
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

/**
 * CSV 上传两步抽屉：
 *   Step 1 选文件 → 校验预览（commit=false）
 *   Step 2 确认 → 真正写库（commit=true）
 */
export function CsvUploadDrawer({
  open,
  onClose,
  table,
}: {
  open: boolean;
  onClose: () => void;
  table: string;
}) {
  const { data: session } = useSession();
  const router = useRouter();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState<"validate" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState(false);

  function reset() {
    setFile(null);
    setPreview(null);
    setError(null);
    setCommitted(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function call(commit: boolean) {
    if (!token || !file) return;
    setBusy(commit ? "commit" : "validate");
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const url = `${API}/api/v1/data/upload-csv?table=${table}&commit=${commit}`;
      const r = await fetch(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const data = (await r.json()) as Preview;
      setPreview(data);
      if (commit) {
        setCommitted(true);
        router.refresh();
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(null);
    }
  }

  const errors = preview?.issues.filter((i) => i.severity === "error") ?? [];
  const warnings = preview?.issues.filter((i) => i.severity === "warning") ?? [];

  return (
    <Drawer
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title={`CSV 上传 · ${TABLE_LABEL[table] ?? table}`}
      width="w-[40rem]"
    >
      <div className="flex flex-col gap-4">
        <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
          <p className="mb-1 font-medium text-foreground">两步流程</p>
          <ol className="ml-4 list-decimal space-y-0.5">
            <li>选 CSV 文件 → 点「校验预览」，仅检查不写库</li>
            <li>若 0 error，点「确认写入」真正落库（含 AuditLog 留痕）</li>
          </ol>
          <p className="mt-1.5">字段定义见 <code className="rounded bg-background px-1 text-[10px]">doc/数据契约_CSV.md</code></p>
        </div>

        <div className="flex flex-col gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setPreview(null);
              setCommitted(false);
            }}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
          />
          {file && (
            <div className="text-xs text-muted-foreground">
              已选：<span className="font-mono">{file.name}</span> · {(file.size / 1024).toFixed(1)} KB
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <Button
            onClick={() => call(false)}
            disabled={!file || busy !== null || committed}
            variant="outline"
            className="flex-1"
          >
            {busy === "validate" ? "校验中..." : "校验预览"}
          </Button>
          <Button
            onClick={() => call(true)}
            disabled={
              !file || busy !== null || !preview || errors.length > 0 || committed
            }
            className="flex-1"
          >
            {busy === "commit" ? "写入中..." : committed ? "✓ 已写入" : "确认写入"}
          </Button>
        </div>

        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {preview && (
          <div className="flex flex-col gap-3 border-t pt-3">
            <div className="flex items-center gap-2 text-sm">
              <Badge variant={errors.length === 0 ? "success" : "destructive"}>
                {preview.valid_rows}/{preview.total_rows} 有效
              </Badge>
              {errors.length > 0 && <Badge variant="destructive">{errors.length} error</Badge>}
              {warnings.length > 0 && <Badge variant="warning">{warnings.length} warn</Badge>}
              {committed && <Badge variant="success">已落库</Badge>}
            </div>

            {preview.sample.length > 0 && (
              <details className="rounded-md border bg-muted/20 p-2 text-xs" open>
                <summary className="cursor-pointer text-muted-foreground">
                  数据预览（前 5 行）
                </summary>
                <div className="mt-1 overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b text-[10px] uppercase text-muted-foreground">
                      <tr>
                        {Object.keys(preview.sample[0]).map((k) => (
                          <th key={k} className="px-2 py-1 text-left font-medium">
                            {k}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="font-mono text-[10px]">
                      {preview.sample.map((row, i) => (
                        <tr key={i} className="border-b border-border/30">
                          {Object.values(row).map((v, j) => (
                            <td key={j} className="px-2 py-1 truncate">
                              {String(v).slice(0, 30)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}

            {(errors.length > 0 || warnings.length > 0) && (
              <details className={cn("rounded-md border p-2 text-xs", errors.length > 0 ? "border-destructive/40 bg-destructive/5" : "border-warning/40 bg-warning/5")} open={errors.length > 0}>
                <summary className="cursor-pointer font-medium">
                  问题清单（{preview.issues.length}）
                </summary>
                <ul className="mt-1.5 ml-4 list-disc space-y-1">
                  {preview.issues.slice(0, 20).map((i, idx) => (
                    <li key={idx} className={i.severity === "error" ? "text-destructive" : "text-warning"}>
                      <span className="font-mono text-[10px]">row {i.row ?? "?"} {i.field ? "· " + i.field : ""}</span>
                      <span className="ml-2">{i.message}</span>
                    </li>
                  ))}
                  {preview.issues.length > 20 && (
                    <li className="text-muted-foreground">... 共 {preview.issues.length} 项，只显示前 20 条</li>
                  )}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>
    </Drawer>
  );
}
