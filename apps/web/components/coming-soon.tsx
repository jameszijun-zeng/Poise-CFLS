import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function ComingSoon({ title, phase, summary }: { title: string; phase: string; summary: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{phase}</CardDescription>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        <p>{summary}</p>
        <p className="mt-2">本页面将在该阶段实现。Phase 0 仅打通登录 + RBAC + AuditLog 基础设施。</p>
      </CardContent>
    </Card>
  );
}
