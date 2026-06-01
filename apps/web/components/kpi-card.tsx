import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Tone = "primary" | "success" | "warning" | "destructive" | "muted";

const TONE_CLS: Record<Tone, { value: string; bar: string; ring: string }> = {
  primary:     { value: "text-primary",       bar: "bg-primary",       ring: "ring-primary/20" },
  success:     { value: "text-success",       bar: "bg-success",       ring: "ring-success/20" },
  warning:     { value: "text-warning",       bar: "bg-warning",       ring: "ring-warning/30" },
  destructive: { value: "text-destructive",   bar: "bg-destructive",   ring: "ring-destructive/30" },
  muted:       { value: "text-foreground/80", bar: "bg-muted",         ring: "ring-border" },
};

export function KpiCard({
  label,
  value,
  unit,
  hint,
  tone = "primary",
  badge,
  trend,
  className,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  tone?: Tone;
  badge?: { text: string; variant?: "success" | "warning" | "destructive" | "default" | "primary" };
  trend?: "up" | "down" | null;
  className?: string;
}) {
  const t = TONE_CLS[tone];
  return (
    <Card className={cn("relative overflow-hidden ring-1", t.ring, className)}>
      {/* 顶部色条 */}
      <div className={cn("absolute inset-x-0 top-0 h-1", t.bar)} />
      <CardContent className="flex flex-col gap-1 px-5 py-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{label}</span>
          {badge && <Badge variant={badge.variant ?? "default"}>{badge.text}</Badge>}
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className={cn("text-3xl font-bold tabular-nums leading-tight", t.value)}>
            {value}
          </span>
          {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
          {trend === "up" && <span className="text-sm text-success">↑</span>}
          {trend === "down" && <span className="text-sm text-destructive">↓</span>}
        </div>
        {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}
