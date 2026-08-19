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
        self.pipeline_calls = []

    def pipeline(self, transaction=False):
        pipeline = FakePipeline()
        self.pipeline_calls.append((transaction, pipeline))
        return pipeline


def test_rag_cost_uses_shared_client_daily_model_and_ttl(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(telemetry, "_redis_client", fake)
    monkeypatch.setattr(telemetry, "_utc_date", lambda: "2026-07-30")

    telemetry.record_llm_cost("user-2", "gpt-5.5", 50, 5)
    telemetry.record_llm_cost("user-2", "gpt-5.5", 25, 2)

    assert len(fake.pipeline_calls) == 2
    commands = fake.pipeline_calls[0][1].commands
    assert any(
        command[1] == "llm:tokens:2026-07-30:user:user-2:rag"
        for command in commands
    )
    assert any(":rag:model:" in command[1] for command in commands)
    assert all(
        command[2:] == (telemetry.RETENTION_SECONDS, True)
        for command in commands
        if command[0] == "expire"
    )
