import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { authOptions } from "@/lib/auth";

import { AuditPanel } from "./audit-panel";
import { UsersPanel } from "./users-panel";

export default async function AdminPage() {
  const session = await getServerSession(authOptions);
  // @ts-expect-error -- extended session
  const role: string = session?.user?.role;

  if (!session) redirect("/login");

  const canManageUsers = role === "admin";
  const canReadAudit = role === "admin" || role === "treasurer";

  if (!canManageUsers && !canReadAudit) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>无权访问</CardTitle>
          <CardDescription>当前角色：{role}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            管理后台仅 admin / treasurer 角色可访问。
          </p>
        </CardContent>
      </Card>
    );
  }

  const defaultTab = canManageUsers ? "users" : "audit";

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold">管理后台</h1>
        <p className="text-sm text-muted-foreground">
          用户/角色 · 审计日志 · 系统设计 §7 可审计性要求
        </p>
      </header>
      <Tabs defaultValue={defaultTab}>
        <TabsList>
          {canManageUsers && <TabsTrigger value="users">用户管理</TabsTrigger>}
          {canReadAudit && <TabsTrigger value="audit">审计日志</TabsTrigger>}
        </TabsList>
        {canManageUsers && (
          <TabsContent value="users">
            <UsersPanel />
          </TabsContent>
        )}
        {canReadAudit && (
          <TabsContent value="audit">
            <AuditPanel />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
