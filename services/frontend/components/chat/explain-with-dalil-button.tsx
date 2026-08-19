"use client";

import React from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import {
  defaultExplanationPrompt,
  type ExplanationContext,
} from "@/lib/explanation-context";
import { useOptionalDalilChat } from "./dalil-chat-provider";

interface ExplainWithDalilButtonProps {
  context: ExplanationContext;
  prompt?: string;
  display?: "icon" | "compact";
  className?: string;
  onBeforeOpen?: () => void;
}

/** A consistent entry point from a derived claim into Dalil's chat. */
export function ExplainWithDalilButton({
  context,
  prompt = defaultExplanationPrompt(context),
  display = "icon",
  className,
  onBeforeOpen,
}: ExplainWithDalilButtonProps) {
  const chat = useOptionalDalilChat();
  const accessibleLabel = `Ask Dalil to explain ${context.title}`;

  // Shared score/checklist components also render in isolated previews and
  // public share pages that intentionally have no authenticated chat shell.
  if (!chat) return null;

  const open = (event: React.MouseEvent<HTMLButtonElement>) => {
    const invoker = event.currentTarget;
    onBeforeOpen?.();
    window.requestAnimationFrame(() =>
      chat.openWithExplanation(prompt, context, {
        invoker: invoker.isConnected ? invoker : null,
      }),
    );
  };

  if (display === "compact") {
    return (
      <Button
        type="button"
        size="sm"
        variant="ghost"
        leadingIcon={Sparkles}
        aria-label={accessibleLabel}
        onClick={open}
        data-explanation-kind={context.kind}
        className={cn(
          "rounded-full border border-brand-border bg-brand-subtle text-brand-fg hover:bg-brand-muted",
          className,
        )}
      >
        Ask Dalil
      </Button>
    );
  }

  return (
    <Tooltip content="Ask Dalil to explain this">
      <Button
        type="button"
        size="sm"
        variant="ghost"
        iconOnly
        leadingIcon={Sparkles}
        aria-label={accessibleLabel}
        onClick={open}
        data-explanation-kind={context.kind}
        className={cn(
          "h-8 w-8 shrink-0 rounded-full border border-brand-border bg-brand-subtle text-brand-fg shadow-e1 hover:-translate-y-0.5 hover:bg-brand-muted hover:shadow-e2",
          className,
        )}
      />
    </Tooltip>
  );
}
