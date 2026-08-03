import hashlib
import os

import psycopg2

from app.core.crawl_state import CrawlStateManager


def _db_url():
    return (
        os.getenv("INGESTION_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://goa:goa_pass@postgres:5432/ingestion_db"
    )


def _reset_tables():
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DROP TABLE IF EXISTS ingestion_runs, crawl_sources, crawl_urls, "
                "crawl_cursors CASCADE"
            )


def test_real_schema_and_conflict_paths():
    _reset_tables()
    manager = CrawlStateManager(db_url=_db_url())
    manager._init_db()

    url = "https://www.mastersportal.com/studies/123/robotics.html"
    manager.mark_url_status("masters_portal", "engineering", url, "extracted")
    manager.mark_url_status("masters_portal", "engineering", url, "scraped")
    manager.mark_page_status(url, "fetched")
    manager.update_cursor(
        "masters_portal",
        "engineering",
        last_page=2,
        scroll_offset=20,
        total_items=25,
    )
    manager.mark_cursor_failure(
        "masters_portal", "engineering", "temporary discovery failure"
    )
    manager.update_cursor(
        "masters_portal",
        "engineering",
        last_page=3,
        scroll_offset=25,
        exhausted=True,
        total_items=25,
    )
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT url_hash, status, page_status, failure_count,
                       last_attempt_at, last_success_at
                FROM crawl_urls
                """
            )
            row = cursor.fetchone()
            assert row[0] == hashlib.sha256(url.encode()).hexdigest()
            assert row[1:4] == ("scraped", "fetched", 0)
            assert row[4] is not None
            assert row[5] is not None
            cursor.execute("SELECT COUNT(*) FROM crawl_urls")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM crawl_cursors")
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                """
                SELECT failure_count, completion_status, error_message,
                       last_attempt_at, last_success_at
                FROM crawl_cursors
                """
            )
            cursor_state = cursor.fetchone()
            assert cursor_state[0:3] == (1, "completed", None)
            assert cursor_state[3] is not None
            assert cursor_state[4] is not None


def test_existing_table_alter_path_adds_all_state_columns():
    _reset_tables()
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE crawl_urls (
                    url_hash VARCHAR(64) PRIMARY KEY,
                    source_name VARCHAR(100) NOT NULL,
                    discipline VARCHAR(100) NOT NULL,
                    url TEXT NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    error_message TEXT,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    manager = CrawlStateManager(db_url=_db_url())
    manager._init_db()

    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'crawl_urls'
                """
            )
            columns = {row[0] for row in cursor.fetchall()}
    assert {
        "page_status",
        "failure_count",
        "last_attempt_at",
        "last_success_at",
        "error_message",
    } <= columns


def test_remaining_is_derived_from_seeded_state():
    _reset_tables()
    manager = CrawlStateManager(db_url=_db_url())
    manager._init_db()
    manager.mark_url_status(
        "masters_portal", "engineering", "https://example.test/done", "scraped"
    )
    manager.mark_url_status(
        "masters_portal", "engineering", "https://example.test/pending", "extracted"
    )
    manager.update_cursor(
        "masters_portal",
        "engineering",
        last_page=2,
        scroll_offset=2,
        exhausted=True,
        total_items=2,
    )

    assert manager.count_remaining(
        "masters_portal", tier=1, discipline="engineering"
    ) == 1


def test_dry_run_manager_leaves_real_database_unchanged():
    _reset_tables()
    writer = CrawlStateManager(db_url=_db_url())
    writer._init_db()
    url = "https://example.test/dry-run-state"
    writer.mark_url_status("masters_portal", "engineering", url, "scraped")

    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT updated_at FROM crawl_urls WHERE url = %s", (url,)
            )
            before = cursor.fetchone()[0]

    dry = CrawlStateManager(db_url=_db_url(), read_only=True)
    dry.mark_url_status("masters_portal", "engineering", url, "failed", "ignored")
    dry.update_cursor("masters_portal", "engineering", 99, scroll_offset=999)
    dry.start_run("00000000-0000-0000-0000-000000000041")
    dry.finish_run(
        "00000000-0000-0000-0000-000000000041",
        completed=False,
        remaining=1,
    )

    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, failure_count, updated_at
                FROM crawl_urls WHERE url = %s
                """,
                (url,),
            )
            row = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM crawl_cursors")
            cursor_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM ingestion_runs WHERE run_id = %s",
                ("00000000-0000-0000-0000-000000000041",),
            )
            run_count = cursor.fetchone()[0]

    assert row == ("scraped", 0, before)
    assert cursor_count == 0
    assert run_count == 0


def test_source_failures_preserve_last_success_and_increment_only_failures():
    _reset_tables()
    manager = CrawlStateManager(db_url=_db_url())
    manager._init_db()
    manager.mark_source_attempt(
        "visa_adapter",
        "source-1",
        "https://example.test/visa",
        succeeded=True,
    )

    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT last_success_at
                FROM crawl_sources
                WHERE source_name = 'visa_adapter' AND source_key = 'source-1'
                """
            )
            successful_at = cursor.fetchone()[0]

    manager.mark_source_attempt(
        "visa_adapter",
        "source-1",
        "https://example.test/visa",
        succeeded=False,
        error_message="blocked",
    )

    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT completion_status, failure_count, error_message,
                       last_attempt_at, last_success_at
                FROM crawl_sources
                WHERE source_name = 'visa_adapter' AND source_key = 'source-1'
                """
            )
            row = cursor.fetchone()

    assert row[0:3] == ("failed", 1, "blocked")
    assert row[3] is not None
    assert row[4] == successful_at
