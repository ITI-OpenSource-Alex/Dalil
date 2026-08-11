"use client";

import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Sparkles } from "lucide-react";
import { Button, Icon } from "@/components/ui";
import { cn } from "@/lib/cn";
import ChatShell from "./chat-shell";

interface ChatWidgetProps {
  open: boolean;
  activated: boolean;
  onOpenChange: (open: boolean) => void;
  draft: string;
  onDraftChange: (value: string) => void;
  focusRequestKey: number;
  busy: boolean;
  unread: boolean;
  onBusyChange: (busy: boolean) => void;
  onResponseComplete: () => void;
  onCloseAutoFocus: (fallback: HTMLButtonElement | null) => void;
}

function useMobileDialog(): { mobile: boolean; ready: boolean } {
  // Read the real viewport for the first interactive client render. Starting
  // at false made a fast mobile tap open a non-modal layer and then switch its
  // mode one effect later, which caused the dialog to close again.
  const [mobile, setMobile] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(max-width: 639px)").matches,
  );
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => setMobile(query.matches);
    update();
    setReady(true);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return { mobile, ready };
}

export default function ChatWidget({
  open,
  activated,
  onOpenChange,
  draft,
  onDraftChange,
  focusRequestKey,
  busy,
  unread,
  onBusyChange,
  onResponseComplete,
  onCloseAutoFocus,
}: ChatWidgetProps) {
  const { mobile, ready: responsiveModeReady } = useMobileDialog();

  const restoreFocus = () => {
    onCloseAutoFocus(
      document.querySelector<HTMLButtonElement>(
        "[data-testid='dalil-chat-pill']",
      ),
    );
  };

  const handleOpenChange = (next: boolean) => {
    onOpenChange(next);
    // Controlled non-modal dialogs do not consistently return focus after an
    // Escape close, so restore it explicitly for keyboard users.
    if (!next) window.requestAnimationFrame(restoreFocus);
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange} modal={mobile}>
      <Button
        size="lg"
        disabled={!responsiveModeReady}
        aria-label="Open Dalil chat"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="dalil-chat-panel"
        onClick={() =>
          // Defer until the opening pointer event is over, matching contextual
          // Ask Dalil buttons and avoiding an immediate outside-dismiss.
          window.requestAnimationFrame(() => handleOpenChange(true))
        }
        className={cn(
          "fixed right-4 z-[1000] rounded-full shadow-e3 print:hidden sm:right-6",
          "bottom-[max(1rem,env(safe-area-inset-bottom))]",
          open && "pointer-events-none opacity-0",
        )}
        data-testid="dalil-chat-pill"
      >
        <Icon icon={Sparkles} size="sm" />
        Ask Dalil
        {busy && (
          <span
            className="ml-1 h-2 w-2 animate-pulse rounded-full bg-accent"
            aria-label="Dalil is replying"
          />
        )}
        {!busy && unread && (
          <span
            className="ml-1 h-2 w-2 rounded-full bg-accent"
            aria-label="New reply from Dalil"
          />
        )}
      </Button>

      <Dialog.Portal forceMount>
        <Dialog.Overlay
          forceMount
          className={cn(
            "fixed inset-0 z-[1050] bg-sage-950/40 backdrop-blur-[2px] sm:hidden",
            open ? "animate-fade-in" : "hidden",
          )}
        />
        <Dialog.Content
          forceMount
          id="dalil-chat-panel"
          data-testid="dalil-chat-panel"
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            restoreFocus();
          }}
          className={cn(
            "fixed z-[1100] flex min-h-0 flex-col overflow-hidden border border-border bg-surface-raised shadow-e4 outline-none print:hidden",
            "inset-x-0 bottom-0 h-[calc(100dvh-4rem)] rounded-t-panel",
            "sm:inset-auto sm:right-6 sm:bottom-20 sm:h-[min(44rem,calc(100dvh-6.5rem))] sm:w-[26rem] sm:rounded-panel",
            open ? "animate-scale-in" : "hidden",
          )}
        >
          <Dialog.Title className="sr-only">Dalil assistant</Dialog.Title>
          <Dialog.Description className="sr-only">
            General-purpose chat with Dalil. Contextual prompts remain editable before sending.
          </Dialog.Description>
          {activated && (
            <ChatShell
              variant="widget"
              draft={draft}
              onDraftChange={onDraftChange}
              focusRequestKey={focusRequestKey}
              onClose={() => handleOpenChange(false)}
              onBusyChange={onBusyChange}
              onResponseComplete={onResponseComplete}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
