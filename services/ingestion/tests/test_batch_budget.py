from app.core.batch import BatchBudget, deadline_from_context


class _Context:
    def get_remaining_time_in_millis(self):
        return 300_000


def test_item_budget_stops_cleanly():
    budget = BatchBudget(max_items=2, deadline=100, clock=lambda: 0)

    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.exhausted is True
    assert budget.consume() is False


def test_deadline_budget_stops_cleanly():
    now = [0.0]
    budget = BatchBudget(max_items=10, deadline=5, clock=lambda: now[0])

    assert budget.consume() is True
    now[0] = 5.0
    assert budget.exhausted is True


def test_context_deadline_reserves_shutdown_margin():
    assert deadline_from_context(
        _Context(),
        wall_clock_budget_s=999,
        safety_margin_s=120,
        clock=lambda: 10,
    ) == 190


def test_cli_deadline_uses_configured_wall_clock_budget():
    assert deadline_from_context(
        None,
        wall_clock_budget_s=600,
        safety_margin_s=120,
        clock=lambda: 10,
    ) == 490
