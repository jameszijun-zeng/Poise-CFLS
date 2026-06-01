import { cn } from "@/lib/utils";

type Column<T> = {
  header: string;
  cell: (row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
  width?: string;
};

export function DataTable<T>({
  rows,
  columns,
  empty = "暂无数据",
  className,
}: {
  rows: T[];
  columns: Column<T>[];
  empty?: string;
  className?: string;
}) {
  if (rows.length === 0) {
    return <p className="py-6 text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <div className={cn("overflow-x-auto rounded-md border", className)}>
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-xs uppercase text-muted-foreground">
          <tr>
            {columns.map((c, i) => (
              <th
                key={i}
                className={cn(
                  "px-3 py-2 font-medium",
                  c.align === "right" && "text-right",
                  c.align === "center" && "text-center",
                )}
                style={c.width ? { width: c.width } : undefined}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b last:border-b-0 hover:bg-muted/30">
              {columns.map((c, j) => (
                <td
                  key={j}
                  className={cn(
                    "px-3 py-2",
                    c.align === "right" && "text-right tabular-nums",
                    c.align === "center" && "text-center",
                  )}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const fmtMoney = (n: number | string) =>
  Number(n).toLocaleString("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 0 });

export const fmtPct = (n: number | string) =>
  `${(Number(n) * 100).toFixed(2)}%`;
