"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

import { SolveButton } from "./solve-button";
import { WhatIfDrawer } from "./whatif-drawer";

export function PlansActionsBar() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        🧪 what-if 沙盘
      </Button>
      <SolveButton />
      <WhatIfDrawer open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
