"use client";

import React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";
import { Button } from "./button";
import { Heading } from "./heading";
import { Text } from "./text";

/* ------------------------------------------------------------------ *
 * Built on @radix-ui/react-dialog rather than hand-rolled.
 *
 * A correct dialog has to trap focus, restore it to the trigger on close,
 * mark the rest of the page aria-hidden, lock body scroll without causing
 * layout shift from the disappearing scrollbar, close on Escape, and
 * handle nested//portalled content. Every one of those is a place where
 * hand-written dialogs go subtly wrong, and none of it is product logic
 * worth owning. SubmitConfirmModal — the codebase's only current modal —
 * implements none of them.
 * ------------------------------------------------------------------ */

const SIZE = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
} as const;

export interface ModalProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Uncontrolled trigger. Omit when driving `open` yourself. */
  children: React.ReactNode;
}

export function Modal({ open, onOpenChange, children }: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {children}
    </Dialog.Root>
  );
}

export const ModalTrigger = Dialog.Trigger;
export const ModalClose = Dialog.Close;

export interface ModalContentProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  /**
   * Required: an accessible name for the dialog. Radix warns without one,
   * and a dialog that announces only "dialog" is unusable non-visually.
   */
  title: React.ReactNode;
  /** Hides the title visually while keeping it announced. */
  titleHidden?: boolean;
  description?: React.ReactNode;
  size?: keyof typeof SIZE;
  /** Hides the corner close button. Escape and overlay click still work. */
  hideCloseButton?: boolean;
  /**
   * Prevents dismissal by Escape or overlay click. Use only for genuinely
   * blocking flows (destructive confirmation, in-flight submission) — it
   * takes away the user's exit.
   */
  dismissible?: boolean;
  footer?: React.ReactNode;
}

export function ModalContent({
  title,
  titleHidden = false,
  description,
  size = "md",
  hideCloseButton = false,
  dismissible = true,
  footer,
  className,
  children,
  ...props
}: ModalContentProps) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay
        className={cn(
          "fixed inset-0 z-1200 bg-sage-950/40 backdrop-blur-[2px]",
          "data-[state=open]:animate-fade-in",
        )}
      />
      <Dialog.Content
        onEscapeKeyDown={dismissible ? undefined : (e) => e.preventDefault()}
        onPointerDownOutside={
          dismissible ? undefined : (e) => e.preventDefault()
        }
        className={cn(
          "fixed top-1/2 left-1/2 z-1300 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2",
          // Tall content scrolls inside the dialog rather than the page, so
          // the header and footer stay put.
          "flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden",
          "rounded-panel border border-border bg-surface-raised shadow-e3",
          "data-[state=open]:animate-scale-in",
          SIZE[size],
          className,
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-4 p-6 pb-0">
          <div className="flex flex-col gap-1.5">
            <Dialog.Title asChild>
              <Heading as="h2" size="lg" className={cn(titleHidden && "sr-only")}>
                {title}
              </Heading>
            </Dialog.Title>
            {description && (
              <Dialog.Description asChild>
                <Text size="sm" tone="muted">
                  {description}
                </Text>
              </Dialog.Description>
            )}
          </div>

          {!hideCloseButton && (
            <Dialog.Close asChild>
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                aria-label="Close dialog"
                className="-mt-1 -mr-1 shrink-0"
              >
                <Icon icon={X} size="sm" />
              </Button>
            </Dialog.Close>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-6">{children}</div>

        {footer && (
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border bg-canvas-subtle p-4 px-6">
            {footer}
          </div>
        )}
      </Dialog.Content>
    </Dialog.Portal>
  );
}
