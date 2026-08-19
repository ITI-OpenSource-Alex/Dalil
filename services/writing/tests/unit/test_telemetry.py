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
    def pipeline(self, transaction=False):
        assert transaction is False
        self.pipeline = FakePipeline()
        return self.pipeline


def test_writing_cost_is_daily_service_scoped_and_expiring(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(telemetry, "_redis_client", fake)
    monkeypatch.setattr(telemetry, "_utc_date", lambda: "2026-07-30")

    telemetry.record_llm_cost("user-3", "claude-opus-5", 80, 8)

    assert any(
        command[1] == "llm:tokens:2026-07-30:user:user-3:writing"
        for command in fake.pipeline.commands
    )
    assert any(":writing:model:" in command[1] for command in fake.pipeline.commands)
    assert all(
        command[2:] == (telemetry.RETENTION_SECONDS, True)
        for command in fake.pipeline.commands
        if command[0] == "expire"
    )
