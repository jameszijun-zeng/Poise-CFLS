import { getServerSession } from "next-auth";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { authOptions } from "@/lib/auth";

const NAV_ITEMS: { href: string; label: string; phase: string }[] = [
  { href: "/dashboard", label: "概览", phase: "P0" },
  { href: "/chat", label: "对话参谋", phase: "P4/P5" },
  { href: "/forecast", label: "13 周看板", phase: "P2/P5" },
  { href: "/plans", label: "方案对比", phase: "P3/P5" },
  { href: "/alerts", label: "预警中心", phase: "P3/P5" },
  { href: "/data", label: "数据录入", phase: "P1" },
  { href: "/accuracy", label: "MAPE 看板", phase: "P2" },
  { href: "/admin", label: "管理后台", phase: "P0" },
];

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  // @ts-expect-error -- extended session fields
  const role: string = session.user?.role ?? "viewer";
  const name = session.user?.name ?? "用户";

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-56 shrink-0 border-r bg-muted/40 p-4 flex flex-col gap-1 overflow-y-auto">
        <div className="px-2 pb-4">
          <div className="text-lg font-semibold">稳盈 / Poise</div>
          <div className="text-xs text-muted-foreground">CFLS Agent</div>
        </div>
        {NAV_ITEMS.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-background"
          >
            <span>{it.label}</span>
            <span className="text-[10px] text-muted-foreground">{it.phase}</span>
          </Link>
        ))}
        <div className="mt-auto border-t pt-3 text-xs text-muted-foreground">
          <div>{name}</div>
          <div>角色：{role}</div>
          <Link href="/api/auth/signout" className="mt-2 inline-block text-primary">
            登出
          </Link>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto bg-background p-6">{children}</main>
    </div>
  );
}
