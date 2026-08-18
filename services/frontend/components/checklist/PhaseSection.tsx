import type { ChecklistItem, Phase } from "@/app/types/checklist";
import ChecklistItemRow from "./ChecklistItemRow";
import { Badge, Card, Heading } from "@/components/ui";

export default function PhaseSection({
  phase,
  items,
  onToggle,
  programId,
  programName,
}: {
  phase: Phase;
  items: ChecklistItem[];
  onToggle: (itemId: string, checked: boolean) => void;
  programId: string;
  programName?: string;
}) {
  if (items.length === 0) {
    return null;
  }

  const doneCount = items.filter((item) => item.checked).length;

  return (
    <Card
      as="section"
      padding="none"
      data-testid="checklist-phase"
      data-phase={phase}
      className="print-avoid-break overflow-hidden"
    >
      <div className="flex items-center justify-between gap-4 border-b border-border bg-canvas-subtle px-5 py-4">
        <Heading as="h2" size="sm">
          {phase}
        </Heading>
        <Badge tone={doneCount === items.length ? "success" : "neutral"} size="sm" pill>
          {doneCount}/{items.length} complete
        </Badge>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <ChecklistItemRow
            key={item.itemId}
            item={item}
            programId={programId}
            programName={programName}
            phase={phase}
            onToggle={(checked) => onToggle(item.itemId, checked)}
          />
        ))}
      </ul>
    </Card>
  );
}
