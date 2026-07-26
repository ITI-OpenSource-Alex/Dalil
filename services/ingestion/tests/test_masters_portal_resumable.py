import pytest
from unittest.mock import MagicMock
from app.core.crawl_state import CrawlStateManager

def test_crawl_state_defaults_when_empty(mocker):
    manager = CrawlStateManager(db_url="postgresql://mock:mock@localhost:5432/mock_db")
    mocker.patch.object(manager, "_get_conn", side_effect=Exception("DB down"))
    cursor = manager.get_cursor("masters_portal", "engineering")
    assert cursor == {"last_page": 1, "scroll_offset": 0, "exhausted": False}
    assert manager.is_url_scraped("https://www.mastersportal.com/studies/123/test.html") is False

def test_crawl_state_update_cursor_queries(mocker):
    manager = CrawlStateManager(db_url="postgresql://mock:mock@localhost:5432/mock_db")
    manager._initialized = True
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    mocker.patch.object(manager, "_get_conn", return_value=mock_conn)

    manager.update_cursor("masters_portal", "engineering", last_page=3, scroll_offset=0, exhausted=False)
    assert mock_cursor.execute.call_count == 1
    call_args = mock_cursor.execute.call_args[0]
    assert "INSERT INTO crawl_cursors" in call_args[0]
    assert call_args[1][0] == "masters_portal"
    assert call_args[1][1] == "engineering"
    assert call_args[1][2] == 3

def test_crawl_state_mark_url_status_queries(mocker):
    manager = CrawlStateManager(db_url="postgresql://mock:mock@localhost:5432/mock_db")
    manager._initialized = True
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    mocker.patch.object(manager, "_get_conn", return_value=mock_conn)

    test_url = "https://www.mastersportal.com/studies/101/robotics.html"
    manager.mark_url_status("masters_portal", "engineering", test_url, "scraped")
    assert mock_cursor.execute.call_count == 1
    call_args = mock_cursor.execute.call_args[0]
    assert "INSERT INTO crawl_urls" in call_args[0]
    assert call_args[1][3] == test_url
    assert call_args[1][4] == "scraped"
