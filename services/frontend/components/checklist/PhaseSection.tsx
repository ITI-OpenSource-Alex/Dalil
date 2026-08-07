import type { ChecklistItem, Phase } from "@/app/types/checklist";
import ChecklistItemRow from "./ChecklistItemRow";

export default function PhaseSection({
  phase,
  items,
  onToggle,
}: {
  phase: Phase;
  items: ChecklistItem[];
  onToggle: (itemId: string, checked: boolean) => void;
}) {
  if (items.length === 0) {
    return null;
  }

  const doneCount = items.filter((item) => item.checked).length;

  return (
    <section data-testid="checklist-phase" data-phase={phase} className="print-avoid-break">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-semibold text-brand-fg">{phase}</h3>
        <span className="text-xs text-fg-subtle">
          {doneCount}/{items.length} complete
        </span>
      </div>
      <ul className="space-y-2">
        {items.map((item) => (
          <ChecklistItemRow
            key={item.itemId}
            item={item}
            onToggle={(checked) => onToggle(item.itemId, checked)}
          />
        ))}
      </ul>
    </section>
  );
}
