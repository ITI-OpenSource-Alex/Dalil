"use client";

import { ArrowLeft, Clock } from "lucide-react";
import type { SkillArea } from "@/app/types/exam";
import { Badge, Button, Card, EmptyState, Text } from "@/components/ui";

// GOA-035/BUG-047 doc 08: replaces the exam shell's dashed-grey
// "Interactive Simulation Workspace" placeholder for skills that aren't
// built yet. Layer 1 (the "Coming soon" badge on /exam's skill cards)
// keeps this from being reached in ordinary use -- this is Layer 2, for
// the case the shell is still reached directly (a stale sessionStorage
// entry, or a manually-typed URL).
const PLANNED_CAPABILITIES: Record<"Listening" | "Speaking", string[]> = {
  Listening: [
    "Seek-disabled audio player",
    "Sequential section progression",
    "A scratch pad for notes",
    "A 10-minute answer-transfer period",
  ],
  Speaking: [
    "The strict 3-part IELTS structure",
    "A 60-second preparation timer",
    "A live waveform visualizer",
    "Holistic 4-agent evaluation",
  ],
};

interface ComingSoonPanelProps {
  skill: SkillArea;
  onBack: () => void;
}

export default function ComingSoonPanel({ skill, onBack }: ComingSoonPanelProps) {
  const capabilities =
    skill === "Listening" || skill === "Speaking"
      ? PLANNED_CAPABILITIES[skill]
      : [];

  return (
    <Card className="max-w-3xl mx-auto my-8">
      <EmptyState
        icon={Clock}
        title={`${skill} simulation isn't built yet`}
        description={`Reading is complete; ${skill} is next. Here's what's already scoped for it:`}
        actions={
          <Button size="sm" leadingIcon={ArrowLeft} onClick={onBack}>
            Back to Skills Workspace
          </Button>
        }
      >
        <Badge tone="brand" pill>
          Coming soon
        </Badge>

        {capabilities.length > 0 && (
          <ul className="mt-2 space-y-2 text-left max-w-sm mx-auto">
            {capabilities.map((capability) => (
              <li key={capability} className="flex items-start gap-2">
                <span
                  className="mt-1.5 h-1.5 w-1.5 rounded-full bg-brand shrink-0"
                  aria-hidden="true"
                />
                <Text size="sm" tone="muted">
                  {capability}
                </Text>
              </li>
            ))}
          </ul>
        )}
      </EmptyState>
    </Card>
  );
}
