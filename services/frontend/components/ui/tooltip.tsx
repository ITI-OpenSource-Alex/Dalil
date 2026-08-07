"use client";

import React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/cn";

/**
 * Wraps the already-installed @radix-ui/react-tooltip so call sites get the
 * house styling and a single Provider configuration.
 *
 * Tooltips are supplementary only. Anything a user *must* read to operate a
 * control belongs in visible text or in the accessible name — a tooltip is
 * unavailable to touch users, who have no hover.
 */

export function TooltipProvider({
  delayDuration = 200,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Provider>) {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration} {...props}>
      {children}
    </TooltipPrimitive.Provider>
  );
}

export interface TooltipProps {
  content: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  /** Disables the tooltip without unmounting the trigger. */
  disabled?: boolean;
  children: React.ReactNode;
}

export function Tooltip({
  content,
  side = "top",
  align = "center",
  disabled = false,
  children,
}: TooltipProps) {
  if (disabled) return <>{children}</>;

  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          align={align}
          sideOffset={6}
          collisionPadding={8}
          className={cn(
            "z-1400 max-w-xs rounded-control bg-surface-inverse px-3 py-1.5",
            "text-sm leading-5 text-fg-inverse shadow-e2",
            "data-[state=delayed-open]:animate-fade-in",
          )}
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-[var(--surface-inverse)]" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
