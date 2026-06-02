"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

import { AdapterImportDrawer } from "./adapter-import-drawer";

export function AdapterImportButton() {
  const { data: session } = useSession();
  // @ts-expect-error
  const role: string = session?.user?.role ?? "viewer";
  const allowed = ["admin", "treasurer", "analyst"].includes(role);
  const [open, setOpen] = useState(false);

  if (!allowed) return null;
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        🔌 数据源适配器
      </Button>
      <AdapterImportDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
