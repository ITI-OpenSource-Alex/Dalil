from app import telemetry


class FakePipeline:
    def __init__(self):
        self.commands = []

    def hincrby(self, key, field, value):
        self.commands.append(("hincrby", key, field, value))
        return self

    def expire(self, key, seconds, nx=False):
        self.commands.append(("expire", key, seconds, nx))
        return self

    def execute(self):
        return [True] * len(self.commands)


class FakeRedis:
    def __init__(self):
        self.pipelines = []

    def pipeline(self, transaction=False):
        assert transaction is False
        pipeline = FakePipeline()
        self.pipelines.append(pipeline)
        return pipeline


def test_record_llm_cost_is_daily_service_scoped_and_retained(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(telemetry, "_redis_client", fake)
    monkeypatch.setattr(telemetry, "_utc_date", lambda: "2026-07-30")

    telemetry.record_llm_cost("user-1", "claude-opus-4-8", 100, 25)

    commands = fake.pipelines[0].commands
    keys = {command[1] for command in commands}
    assert "llm:tokens:2026-07-30:user:user-1:orchestration" in keys
    assert "llm:tokens:2026-07-30:global" in keys
    assert any(":orchestration:model:" in key for key in keys)
    assert all(
        command[2:] == (telemetry.RETENTION_SECONDS, True)
        for command in commands
        if command[0] == "expire"
    )


def test_record_llm_cost_uses_new_key_on_next_utc_day(monkeypatch):
    fake = FakeRedis()
    dates = iter(("2026-07-30", "2026-07-31"))
    monkeypatch.setattr(telemetry, "_redis_client", fake)
    monkeypatch.setattr(telemetry, "_utc_date", lambda: next(dates))

    telemetry.record_llm_cost("user-1", "claude-opus-4-8", 10, 1)
    telemetry.record_llm_cost("user-1", "claude-opus-4-8", 10, 1)

    first_keys = {command[1] for command in fake.pipelines[0].commands}
    second_keys = {command[1] for command in fake.pipelines[1].commands}
    assert all(":2026-07-30:" in key for key in first_keys)
    assert all(":2026-07-31:" in key for key in second_keys)
