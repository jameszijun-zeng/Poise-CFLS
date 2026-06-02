"use client";

import { type ReactNode, useState } from "react";

import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data-table";

import { CsvUploadDrawer } from "./csv-upload-drawer";

/**
 * 只读列表 + CSV 上传通用面板（用于结构性数据，手工增删改频率低）。
 * 用 CSV 上传完成批量增删改更高效，而非逐条手工编辑。
 */
export function ReadonlyWithCsv<T>({
  rows,
  columns,
  table,
  summary,
  empty,
}: {
  rows: T[];
  columns: Parameters<typeof DataTable<T>>[0]["columns"];
  table: string;
  summary?: ReactNode;
  empty?: string;
}) {
  const [showCsv, setShowCsv] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          共 <b className="text-foreground">{rows.length}</b> 条
          {summary && <span className="ml-2">{summary}</span>}
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowCsv(true)}>
          📤 CSV 上传 / 批量改
        </Button>
      </div>
      <DataTable rows={rows} columns={columns} empty={empty ?? "尚无数据"} />
      <CsvUploadDrawer
        open={showCsv}
        onClose={() => setShowCsv(false)}
        table={table}
      />
    </div>
  );
}
