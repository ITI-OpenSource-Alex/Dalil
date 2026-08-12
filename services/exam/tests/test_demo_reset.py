from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.api import demo


class FakeConnection:
    def __init__(self):
        self.commands = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetch(self, query, *args):
        self.commands.append((query, args))
        return []

    async def execute(self, query, *args):
        self.commands.append((query, args))
        return "INSERT 0 1"


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.asyncio
async def test_demo_reset_creates_three_ordered_reading_results(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(demo.db, "pool", pool)

    history = await demo.reset_reading_history(uuid4())

    assert [row["band_score"] for row in history] == [5.5, 6.0, 6.5]
    assert [row["graded_at"] for row in history] == sorted(
        row["graded_at"] for row in history
    )
    result_inserts = [
        command
        for command in pool.connection.commands
        if "INSERT INTO exam_results" in command[0]
    ]
    session_inserts = [
        command
        for command in pool.connection.commands
        if "INSERT INTO exam_sessions" in command[0]
    ]
    assert all("'scored'" in command[0] for command in session_inserts)
    assert len(result_inserts) == 3
    assert all('"demo_seed": "goa-047"' in command[1][-1] for command in result_inserts)
