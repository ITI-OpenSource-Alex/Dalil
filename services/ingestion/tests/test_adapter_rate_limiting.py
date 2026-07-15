import pytest

from app.adapters.base_adapter import BaseAdapter
from app.adapters.base_playwright_adapter import BasePlaywrightAdapter


class _StubAdapter(BaseAdapter):
    """Minimal concrete BaseAdapter subclass used only to exercise the base class's own
    scrape() template method and constructor defaults, without depending on any real adapter."""

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        return [{"content": html}]


class _StubPlaywrightAdapter(BasePlaywrightAdapter):
    """Minimal concrete BasePlaywrightAdapter subclass used only to exercise the base class's
    own scrape() template method and constructor defaults, without depending on any real adapter."""

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        return [{"content": html}]


@pytest.mark.asyncio
async def test_base_adapter_default_delay_is_one_to_two_seconds(mocker):
    adapter = _StubAdapter(
        base_url="https://example.test",
        target_url="https://example.test/page",
        source_name="stub_source",
        category="test",
        country="Testland",
    )

    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=True)
    mocker.patch.object(adapter, "fetch_page", return_value="<html></html>")
    mock_delay = mocker.patch("app.adapters.base_adapter.polite_delay")

    await adapter.scrape()

    mock_delay.assert_called_once_with(1.0, 2.0)


@pytest.mark.asyncio
async def test_base_adapter_override_delay_is_two_to_three_seconds(mocker):
    adapter = _StubAdapter(
        base_url="https://example.test",
        target_url="https://example.test/page",
        source_name="stub_source",
        category="test",
        country="Testland",
        min_delay=2.0,
        max_delay=3.0,
    )

    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=True)
    mocker.patch.object(adapter, "fetch_page", return_value="<html></html>")
    mock_delay = mocker.patch("app.adapters.base_adapter.polite_delay")

    await adapter.scrape()

    mock_delay.assert_called_once_with(2.0, 3.0)


@pytest.mark.asyncio
async def test_base_playwright_adapter_default_delay_is_one_to_two_seconds(mocker):
    adapter = _StubPlaywrightAdapter(
        base_url="https://example.test",
        target_url="https://example.test/page",
        source_name="stub_source",
        category="test",
        country="Testland",
        wait_selector="body",
    )

    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=True)
    mocker.patch.object(adapter, "fetch_page", return_value="<html></html>")
    mock_delay = mocker.patch("app.adapters.base_playwright_adapter.polite_delay")

    await adapter.scrape()

    mock_delay.assert_called_once_with(1.0, 2.0)


@pytest.mark.asyncio
async def test_base_playwright_adapter_override_delay_is_two_to_three_seconds(mocker):
    adapter = _StubPlaywrightAdapter(
        base_url="https://example.test",
        target_url="https://example.test/page",
        source_name="stub_source",
        category="test",
        country="Testland",
        wait_selector="body",
        min_delay=2.0,
        max_delay=3.0,
    )

    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=True)
    mocker.patch.object(adapter, "fetch_page", return_value="<html></html>")
    mock_delay = mocker.patch("app.adapters.base_playwright_adapter.polite_delay")

    await adapter.scrape()

    mock_delay.assert_called_once_with(2.0, 3.0)
