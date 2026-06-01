"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DataTable } from "@/components/data-table";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

type AuditLog = {
  id: number;
  occurred_at: string;
  actor_user_id: string | null;
  actor_role: string | null;
  event_type: string;
  method: string | null;
  path: string | null;
  status_code: number | null;
  duration_ms: number | null;
  payload: Record<string, unknown> | null;
  notes: string | null;
};

const PAGE_SIZE = 30;

const STATUS_TONE = (s: number | null): "success" | "warning" | "destructive" | "default" => {
  if (!s) return "default";
  if (s >= 500) return "destructive";
  if (s >= 400) return "warning";
  if (s >= 200) return "success";
  return "default";
};

export function AuditPanel() {
  const { data: session } = useSession();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [items, setItems] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [eventType, setEventType] = useState("");
  const [actorRole, setActorRole] = useState("");
  const [hours, setHours] = useState<number | "">("");
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    fetch(`${API}/api/v1/admin/audit-logs/event-types`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setEventTypes)
      .catch(() => {});
  }, [token]);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (eventType) qs.set("event_type", eventType);
      if (actorRole) qs.set("actor_role", actorRole);
      if (hours) qs.set("hours", String(hours));
      const r = await fetch(`${API}/api/v1/admin/audit-logs?${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [token, offset, eventType, actorRole, hours]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>审计日志检索</CardTitle>
        <CardDescription>
          HTTP 写操作 + LLM 调用 + 方案采纳/否决 + 数据导入等全程留痕 · 共 {total} 条
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {/* 过滤条 */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            value={eventType}
            onChange={(e) => {
              setEventType(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">全部事件</option>
            {eventTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            value={actorRole}
            onChange={(e) => {
              setActorRole(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">全部角色</option>
            <option value="admin">admin</option>
            <option value="treasurer">treasurer</option>
            <option value="analyst">analyst</option>
            <option value="viewer">viewer</option>
          </select>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            value={hours}
            onChange={(e) => {
              setHours(e.target.value ? Number(e.target.value) : "");
              setOffset(0);
            }}
          >
            <option value="">全部时间</option>
            <option value="1">最近 1 小时</option>
            <option value="24">最近 24 小时</option>
            <option value="168">最近 7 天</option>
            <option value="720">最近 30 天</option>
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            {loading ? "..." : "刷新"}
          </Button>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
            >
              上一页
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
            >
              下一页
            </Button>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DataTable
          rows={items}
          columns={[
            { header: "ID", cell: (r) => r.id, width: "5rem", align: "right" },
            {
              header: "时间",
              cell: (r) => new Date(r.occurred_at).toLocaleString("zh-CN"),
            },
            {
              header: "事件",
              cell: (r) => <code className="text-xs">{r.event_type}</code>,
            },
            {
              header: "角色",
              cell: (r) =>
                r.actor_role ? <Badge variant="default">{r.actor_role}</Badge> : "-",
              align: "center",
            },
            { header: "方法", cell: (r) => r.method ?? "-", align: "center" },
            {
              header: "路径",
              cell: (r) => (
                <code className="text-xs text-muted-foreground">{r.path ?? "-"}</code>
              ),
            },
            {
              header: "状态",
              cell: (r) =>
                r.status_code ? (
                  <Badge variant={STATUS_TONE(r.status_code)}>{r.status_code}</Badge>
                ) : (
                  "-"
                ),
              align: "center",
            },
            {
              header: "耗时",
              cell: (r) => (r.duration_ms ? `${r.duration_ms} ms` : "-"),
              align: "right",
            },
            {
              header: "",
              cell: (r) => (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setOpenRow(openRow === r.id ? null : r.id)}
                >
                  {openRow === r.id ? "收起" : "详情"}
                </Button>
              ),
              align: "center",
            },
          ]}
          empty="无符合条件的记录"
        />

        {openRow && (
          <Card className="border-dashed">
            <CardContent className="py-3">
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs">
                {JSON.stringify(items.find((i) => i.id === openRow) ?? {}, null, 2)}
              </pre>
            </CardContent>
          </Card>
        )}
      </CardContent>
    </Card>
  );
}
