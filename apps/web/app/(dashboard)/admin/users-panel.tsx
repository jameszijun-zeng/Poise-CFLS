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
import { Input } from "@/components/ui/input";

type User = {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "treasurer" | "analyst" | "viewer";
  is_active: boolean;
  created_at: string;
  entity_id: string;
};

const ROLES = ["admin", "treasurer", "analyst", "viewer"] as const;
const ROLE_LABEL: Record<string, string> = {
  admin: "管理员",
  treasurer: "资金主管",
  analyst: "出纳分析师",
  viewer: "只读",
};
const ROLE_TONE: Record<string, "destructive" | "primary" | "warning" | "default"> = {
  admin: "destructive",
  treasurer: "primary",
  analyst: "warning",
  viewer: "default",
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export function UsersPanel() {
  const { data: session } = useSession();
  // @ts-expect-error
  const token: string | undefined = session?.accessToken;

  const [users, setUsers] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    username: "",
    display_name: "",
    password: "",
    role: "viewer" as User["role"],
  });

  const load = useCallback(async () => {
    if (!token) return;
    setError(null);
    try {
      const r = await fetch(`${API}/api/v1/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(await r.text());
      setUsers(await r.json());
    } catch (e) {
      setError(String(e));
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!token || !form.username || !form.display_name || form.password.length < 6) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/v1/admin/users`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      setForm({ username: "", display_name: "", password: "", role: "viewer" });
      await load();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(u: User) {
    if (!token) return;
    setBusy(true);
    try {
      await fetch(`${API}/api/v1/admin/users/${u.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !u.is_active }),
      });
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function setRole(u: User, role: User["role"]) {
    if (!token) return;
    setBusy(true);
    try {
      await fetch(`${API}/api/v1/admin/users/${u.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>创建用户</CardTitle>
          <CardDescription>仅 admin 角色可见。密码至少 6 位。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
            <Input
              placeholder="用户名"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
            <Input
              placeholder="显示名"
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
            <Input
              type="password"
              placeholder="密码（≥6 位）"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]} ({r})
                </option>
              ))}
            </select>
            <Button onClick={create} disabled={busy}>
              {busy ? "..." : "创建"}
            </Button>
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>用户列表（{users.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={users}
            columns={[
              { header: "用户名", cell: (u) => u.username },
              { header: "显示名", cell: (u) => u.display_name },
              {
                header: "角色",
                cell: (u) => (
                  <select
                    value={u.role}
                    onChange={(e) => setRole(u, e.target.value as User["role"])}
                    disabled={busy}
                    className="rounded border bg-background px-2 py-1 text-xs"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                ),
                align: "center",
              },
              {
                header: "标签",
                cell: (u) => <Badge variant={ROLE_TONE[u.role]}>{u.role}</Badge>,
                align: "center",
              },
              {
                header: "状态",
                cell: (u) =>
                  u.is_active ? (
                    <Badge variant="success">激活</Badge>
                  ) : (
                    <Badge variant="default">停用</Badge>
                  ),
                align: "center",
              },
              {
                header: "操作",
                cell: (u) => (
                  <Button size="sm" variant="outline" onClick={() => toggleActive(u)} disabled={busy}>
                    {u.is_active ? "停用" : "激活"}
                  </Button>
                ),
                align: "center",
              },
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
