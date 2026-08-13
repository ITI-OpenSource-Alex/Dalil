"use client";

import React from "react";
import { Sparkles } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { useDalilChat } from "./dalil-chat-provider";

interface AskDalilButtonProps
  extends Omit<ButtonProps, "asChild" | "onClick" | "type"> {
  prompt: string;
  /** Runs before the chat opens, e.g. to close a programme details modal. */
  onBeforeOpen?: () => void;
}

export function AskDalilButton({
  prompt,
  onBeforeOpen,
  children = "Ask Dalil",
  leadingIcon = Sparkles,
  ...buttonProps
}: AskDalilButtonProps) {
  const { openWithPrompt } = useDalilChat();

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    const invoker = event.currentTarget;
    onBeforeOpen?.();

    // Open after this pointer event finishes. Radix's dismissable layer would
    // otherwise see the same click that created the non-modal panel as an
    // outside click and immediately close it. The delay also lets a source
    // modal finish closing before the chat focus manager starts.
    window.requestAnimationFrame(() =>
      openWithPrompt(prompt, { invoker: invoker.isConnected ? invoker : null }),
    );
  };

  return (
    <Button
      type="button"
      leadingIcon={leadingIcon}
      onClick={handleClick}
      {...buttonProps}
    >
      {children}
    </Button>
  );
}
