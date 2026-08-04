import hashlib
import os
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import structlog

from app.core.migrations import run_migrations


logger = structlog.get_logger(__name__)


class CrawlStateUnavailable(RuntimeError):
    """Raised when a cost-bearing crawl cannot prove its persisted state."""


class CrawlStateManager:
    """Persistent, fail-closed crawl state scoped to one ingestion run."""

    def __init__(self, db_url: Optional[str] = None, read_only: bool = False):
        self.db_url = (
            db_url
            or os.getenv("INGESTION_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or "postgresql://goa:goa_pass@localhost:5432/ingestion_db"
        )
        self._initialized = False
        self.read_only = read_only

    def _get_conn(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _raise_unavailable(self, operation: str, error: Exception):
        logger.error("crawl_state_unavailable", operation=operation, error=str(error))
        raise CrawlStateUnavailable(
            f"Crawl state unavailable during {operation}; refusing a fail-open re-crawl"
        ) from error

    def _init_db(self):
        if self._initialized:
            return
        try:
            run_migrations(self.db_url, repair_existing=True)
            self._initialized = True
        except Exception as error:
            self._initialized = False
            self._raise_unavailable("schema initialization", error)

    def get_cursor(self, source_name: str, discipline: str) -> Dict[str, Any]:
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT last_page, next_cursor, scroll_offset, total_items,
                               exhausted, completion_status
                        FROM crawl_cursors
                        WHERE source_name = %s AND discipline = %s;
                        """,
                        (source_name, discipline),
                    )
                    row = cursor.fetchone()
            if row:
                return {
                    "last_page": row["last_page"],
                    "next_cursor": row["next_cursor"],
                    "scroll_offset": row["scroll_offset"],
                    "total_items": row["total_items"],
                    "exhausted": bool(row["exhausted"]),
                    "completion_status": row["completion_status"],
                }
            return {
                "last_page": 1,
                "next_cursor": 0,
                "scroll_offset": 0,
                "total_items": None,
                "exhausted": False,
                "completion_status": "pending",
            }
        except Exception as error:
            self._raise_unavailable("cursor read", error)

    def update_cursor(
        self,
        source_name: str,
        discipline: str,
        last_page: int,
        scroll_offset: int = 0,
        exhausted: bool = False,
        total_items: int | None = None,
    ):
        if self.read_only:
            logger.info(
                "crawl_state_write_suppressed",
                op="update_cursor",
                source_name=source_name,
                discipline=discipline,
                last_page=last_page,
            )
            return
        self._init_db()
        completion_status = "completed" if exhausted else "in_progress"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawl_cursors (
                            source_name, discipline, last_page, next_cursor,
                            scroll_offset, total_items, exhausted, completion_status,
                            last_attempt_at, last_success_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
                        ON CONFLICT (source_name, discipline) DO UPDATE SET
                            last_page = EXCLUDED.last_page,
                            next_cursor = EXCLUDED.next_cursor,
                            scroll_offset = EXCLUDED.scroll_offset,
                            total_items = COALESCE(EXCLUDED.total_items, crawl_cursors.total_items),
                            exhausted = EXCLUDED.exhausted,
                            completion_status = EXCLUDED.completion_status,
                            last_attempt_at = NOW(),
                            last_success_at = NOW(),
                            error_message = NULL,
                            updated_at = NOW();
                        """,
                        (
                            source_name,
                            discipline,
                            last_page,
                            scroll_offset,
                            scroll_offset,
                            total_items,
                            exhausted,
                            completion_status,
                        ),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("cursor update", error)

    def mark_cursor_failure(
        self, source_name: str, discipline: str, error_message: str
    ):
        if self.read_only:
            return
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawl_cursors (
                            source_name, discipline, completion_status,
                            last_attempt_at, failure_count, error_message, updated_at
                        )
                        VALUES (%s, %s, 'failed', NOW(), 1, %s, NOW())
                        ON CONFLICT (source_name, discipline) DO UPDATE SET
                            completion_status = 'failed',
                            last_attempt_at = NOW(),
                            failure_count = crawl_cursors.failure_count + 1,
                            error_message = EXCLUDED.error_message,
                            updated_at = NOW();
                        """,
                        (source_name, discipline, error_message),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("cursor failure update", error)

    def is_url_scraped(self, url: str) -> bool:
        return self._url_status(url, "status", "scraped")

    def is_page_fetched(self, url: str) -> bool:
        return self._url_status(url, "page_status", "fetched")

    def _url_status(self, url: str, column: str, expected: str) -> bool:
        self._init_db()
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT {column} FROM crawl_urls WHERE url_hash = %s;",
                        (url_hash,),
                    )
                    row = cursor.fetchone()
            return bool(row and row[column] == expected)
        except Exception as error:
            self._raise_unavailable(f"{column} read", error)

    def mark_page_status(
        self, url: str, page_status: str, error_message: Optional[str] = None
    ):
        if self.read_only:
            logger.info(
                "crawl_state_write_suppressed",
                op="mark_page_status",
                url=url,
                page_status=page_status,
            )
            return
        self._init_db()
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        failed = page_status == "failed"
        succeeded = page_status == "fetched"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawl_urls
                        SET page_status = %s,
                            failure_count = failure_count + %s,
                            error_message = CASE WHEN %s THEN NULL
                                                 ELSE COALESCE(%s, error_message) END,
                            last_attempt_at = NOW(),
                            last_success_at = CASE WHEN %s THEN NOW()
                                                   ELSE last_success_at END,
                            updated_at = NOW()
                        WHERE url_hash = %s;
                        """,
                        (
                            page_status,
                            1 if failed else 0,
                            succeeded,
                            error_message,
                            succeeded,
                            url_hash,
                        ),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("page status update", error)

    def mark_url_status(
        self,
        source_name: str,
        discipline: str,
        url: str,
        status: str,
        error_message: Optional[str] = None,
    ):
        if self.read_only:
            logger.info(
                "crawl_state_write_suppressed",
                op="mark_url_status",
                url=url,
                status=status,
            )
            return
        self._init_db()
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        failed = status == "failed"
        succeeded = status == "scraped"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawl_urls (
                            url_hash, source_name, discipline, url, status, attempts,
                            failure_count, error_message, last_attempt_at,
                            last_success_at, updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, 1, %s, %s, NOW(),
                            CASE WHEN %s THEN NOW() ELSE NULL END, NOW()
                        )
                        ON CONFLICT (url_hash) DO UPDATE SET
                            source_name = EXCLUDED.source_name,
                            discipline = EXCLUDED.discipline,
                            status = EXCLUDED.status,
                            attempts = crawl_urls.attempts + CASE WHEN %s THEN 1 ELSE 0 END,
                            failure_count = crawl_urls.failure_count + CASE WHEN %s THEN 1 ELSE 0 END,
                            error_message = CASE WHEN %s THEN NULL
                                                 ELSE EXCLUDED.error_message END,
                            last_attempt_at = NOW(),
                            last_success_at = CASE WHEN %s THEN NOW()
                                                   ELSE crawl_urls.last_success_at END,
                            updated_at = NOW();
                        """,
                        (
                            url_hash,
                            source_name,
                            discipline,
                            url,
                            status,
                            1 if failed else 0,
                            error_message,
                            succeeded,
                            failed,
                            failed,
                            succeeded,
                            succeeded,
                        ),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("URL status update", error)

    def mark_source_attempt(
        self,
        source_name: str,
        source_key: str,
        source_url: str,
        *,
        succeeded: bool,
        error_message: str | None = None,
    ):
        if self.read_only:
            return
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawl_sources (
                            source_name, source_key, source_url, completion_status,
                            last_attempt_at, last_success_at, failure_count,
                            error_message, updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s, NOW(),
                            CASE WHEN %s THEN NOW() ELSE NULL END,
                            %s, %s, NOW()
                        )
                        ON CONFLICT (source_name, source_key) DO UPDATE SET
                            source_url = EXCLUDED.source_url,
                            completion_status = EXCLUDED.completion_status,
                            last_attempt_at = NOW(),
                            last_success_at = CASE WHEN %s THEN NOW()
                                                   ELSE crawl_sources.last_success_at END,
                            failure_count = crawl_sources.failure_count + CASE WHEN %s THEN 0 ELSE 1 END,
                            error_message = CASE WHEN %s THEN NULL
                                                 ELSE EXCLUDED.error_message END,
                            updated_at = NOW();
                        """,
                        (
                            source_name,
                            source_key,
                            source_url,
                            "completed" if succeeded else "failed",
                            succeeded,
                            0 if succeeded else 1,
                            error_message,
                            succeeded,
                            succeeded,
                            succeeded,
                        ),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("source state update", error)

    def count_remaining(
        self, source_name: str, *, tier: int, discipline: str | None = None
    ) -> int:
        self._init_db()
        status_column = "status" if tier == 1 else "page_status"
        completed_value = "scraped" if tier == 1 else "fetched"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) AS remaining
                        FROM crawl_urls
                        WHERE source_name = %s
                          AND (%s::text IS NULL OR discipline = %s)
                          AND {status_column} IS DISTINCT FROM %s;
                        """,
                        (source_name, discipline, discipline, completed_value),
                    )
                    known_remaining = int(cursor.fetchone()["remaining"])
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(GREATEST(total_items - scroll_offset, 0)), 0)
                               AS undiscovered
                        FROM crawl_cursors
                        WHERE source_name = %s
                          AND (%s::text IS NULL OR discipline = %s)
                          AND exhausted IS FALSE;
                        """,
                        (source_name, discipline, discipline),
                    )
                    undiscovered = int(cursor.fetchone()["undiscovered"])
            # Pending URL rows belong to the cursor's unadvanced suffix. Taking
            # the maximum avoids counting the same extracted-but-unacknowledged
            # item once as a URL and again inside total_items - scroll_offset.
            return max(known_remaining, undiscovered)
        except Exception as error:
            self._raise_unavailable("remaining count", error)

    def get_last_success_at(self, source_name: str):
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT MAX(value) AS last_success_at
                        FROM (
                            SELECT last_success_at AS value
                            FROM crawl_urls WHERE source_name = %s
                            UNION ALL
                            SELECT last_success_at
                            FROM crawl_cursors WHERE source_name = %s
                            UNION ALL
                            SELECT last_success_at
                            FROM crawl_sources WHERE source_name = %s
                        ) successes;
                        """,
                        (source_name, source_name, source_name),
                    )
                    row = cursor.fetchone()
            return row["last_success_at"] if row else None
        except Exception as error:
            self._raise_unavailable("source success read", error)

    def start_run(self, run_id: str):
        if self.read_only:
            return
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO ingestion_runs (run_id) VALUES (%s) ON CONFLICT DO NOTHING;",
                        (run_id,),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("run start", error)

    def finish_run(
        self,
        run_id: str,
        *,
        completed: bool,
        remaining: int,
        error_message: str | None = None,
    ):
        if self.read_only:
            return
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE ingestion_runs
                        SET finished_at = NOW(),
                            completion_status = %s,
                            remaining = %s,
                            error_message = %s
                        WHERE run_id = %s;
                        """,
                        (
                            "completed" if completed else "partial",
                            remaining,
                            error_message,
                            run_id,
                        ),
                    )
                conn.commit()
        except Exception as error:
            self._raise_unavailable("run completion", error)


# Kept only for backwards-compatible direct adapter construction. The canonical
# runner creates and injects a fresh manager for every invocation.
crawl_state = CrawlStateManager()
