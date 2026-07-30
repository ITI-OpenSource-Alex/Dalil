import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class BatchBudget:
    max_items: int
    deadline: float
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    consumed: int = 0

    @property
    def exhausted(self) -> bool:
        return self.consumed >= self.max_items or self.clock() >= self.deadline

    @property
    def remaining_items(self) -> int:
        return max(0, self.max_items - self.consumed)

    def consume(self, count: int = 1) -> bool:
        if self.exhausted:
            return False
        self.consumed += count
        return True


def deadline_from_context(
    context,
    *,
    wall_clock_budget_s: float,
    safety_margin_s: float = 120,
    clock: Callable[[], float] = time.monotonic,
) -> float:
    if context is not None and hasattr(context, "get_remaining_time_in_millis"):
        available_s = max(
            0,
            context.get_remaining_time_in_millis() / 1000 - safety_margin_s,
        )
    else:
        available_s = max(0, wall_clock_budget_s - safety_margin_s)
    return clock() + available_s
