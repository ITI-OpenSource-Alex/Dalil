"use client";

import React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/cn";

/* Radix supplies the roving tabindex, arrow-key/Home/End navigation and the
   tab<->panel aria wiring. The codebase's current SectionTabs is a row of
   plain buttons: no arrow keys, no aria-selected, no panel association. */

export const Tabs = TabsPrimitive.Root;

export type TabsVariant = "underline" | "pill";

const LIST: Record<TabsVariant, string> = {
  underline: "flex items-center gap-1 border-b border-border",
  pill: "inline-flex items-center gap-1 rounded-control bg-canvas-inset p-1",
};

const TRIGGER: Record<TabsVariant, string> = {
  underline:
    "relative -mb-px border-b-2 border-transparent px-4 py-2.5 text-sm font-medium text-fg-subtle " +
    "transition-[color,border-color] duration-120 ease-out " +
    "hover:text-fg " +
    "data-[state=active]:border-brand data-[state=active]:text-brand-fg " +
    "disabled:pointer-events-none disabled:opacity-50",
  pill:
    "rounded-[calc(var(--radius-control)-0.25rem)] px-3.5 py-1.5 text-sm font-medium text-fg-subtle " +
    "transition-[background-color,color,box-shadow] duration-120 ease-out " +
    "hover:text-fg " +
    "data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-e1 " +
    "disabled:pointer-events-none disabled:opacity-50",
};

const VariantContext = React.createContext<TabsVariant>("underline");

export interface TabsListProps
  extends React.ComponentPropsWithoutRef<typeof TabsPrimitive.List> {
  variant?: TabsVariant;
  /**
   * What a tab row does when it is wider than its container.
   *
   * Defaults to "scroll", and deliberately so: triggers are whitespace-nowrap
   * and shrink-0, so a row that cannot scroll pushes its container wider than
   * the viewport instead. Making overflow opt-in meant every consumer had to
   * remember it — and the first one that forgot (this component's own style
   * guide, at 390px) produced page-wide horizontal scroll.
   *
   * "wrap" is available for rows that genuinely read better on two lines.
   */
  overflow?: "scroll" | "wrap";
}

export function TabsList({
  variant = "underline",
  overflow = "scroll",
  className,
  children,
  ...props
}: TabsListProps) {
  return (
    <VariantContext.Provider value={variant}>
      <TabsPrimitive.List
        className={cn(
          LIST[variant],
          // max-w-full plus a scroll container caps the intrinsic min-content
          // width at zero, which is what stops a long row from stretching a
          // grid or flex parent.
          overflow === "scroll"
            ? "max-w-full overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            : "flex-wrap",
          className,
        )}
        {...props}
      >
        {children}
      </TabsPrimitive.List>
    </VariantContext.Provider>
  );
}

export function TabsTrigger({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) {
  const variant = React.useContext(VariantContext);
  return (
    <TabsPrimitive.Trigger
      className={cn("shrink-0 whitespace-nowrap", TRIGGER[variant], className)}
      {...props}
    >
      {children}
    </TabsPrimitive.Trigger>
  );
}

export function TabsPanel({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      // Radix leaves the panel focusable so keyboard users can Tab from the
      // tab into its content; the outline would otherwise appear on a
      // full-width block, which looks like a bug. The ring is kept for
      // keyboard focus only.
      className={cn("mt-4 focus-visible:outline-none", className)}
      {...props}
    >
      {children}
    </TabsPrimitive.Content>
  );
}
