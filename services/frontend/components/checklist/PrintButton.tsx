"use client";

import { FileDown } from "lucide-react";
import { Button } from "@/components/ui";

export default function PrintButton() {
  return (
    <Button
      variant="secondary"
      leadingIcon={FileDown}
      onClick={() => window.print()}
      className="print-hidden"
    >
      Export as PDF
    </Button>
  );
}
