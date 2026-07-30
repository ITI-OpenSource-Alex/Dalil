import hashlib
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import structlog
from typing import Dict, Any, Optional

logger = structlog.get_logger(__name__)

class CrawlStateManager:
    """Manages crawl cursors and URL scraping status across execution runs.

    Uses persistent PostgreSQL storage (ingestion_db) so interrupted crawls resume
    without restarting from page 1 or re-scraping completed URLs.
    """

    def __init__(self, db_url: Optional[str] = None, read_only: bool = False):
        self.db_url = db_url or os.getenv(
            "INGESTION_DATABASE_URL",
            "postgresql://goa:goa_pass@localhost:5432/ingestion_db"
        )
        self._initialized = False
        # Dry-run guard. The adapters write crawl state DURING the scrape, long before
        # handle_ingestion reaches its `if dry_run:` branch, so a dry run was marking
        # URLs 'extracted'/'fetched' and silently making the next REAL run skip them.
        # That is worse than the criterion it violates: a rehearsal quietly suppressed
        # the thing it was rehearsing. The flag lives here rather than being threaded
        # through every adapter so that a future write site is covered by default.
        self.read_only = read_only

    def _get_conn(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _init_db(self):
        if self._initialized:
            return
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    # Page-level search cursor: tracks (source_name, discipline) pagination
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS crawl_cursors (
                            source_name VARCHAR(100) NOT NULL,
                            discipline VARCHAR(100) NOT NULL,
                            last_page INTEGER DEFAULT 1,
                            scroll_offset INTEGER DEFAULT 0,
                            exhausted BOOLEAN DEFAULT FALSE,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (source_name, discipline)
                        );
                    """)
                    # URL-level state tracker
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS crawl_urls (
                            url_hash VARCHAR(64) PRIMARY KEY,
                            source_name VARCHAR(100) NOT NULL,
                            discipline VARCHAR(100) NOT NULL,
                            url TEXT NOT NULL,
                            -- Tier 1 axis: is the structured row ingested?
                            -- 'pending' | 'extracted' | 'scraped' | 'failed'
                            status VARCHAR(30) NOT NULL,
                            -- Tier 2 axis: has the page been fetched for the document
                            -- corpus? Separate on purpose — a single flag would make
                            -- Tier 2 skip everything Tier 1 already covered.
                            page_status VARCHAR(30) NULL,
                            attempts INTEGER DEFAULT 0,
                            error_message TEXT,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    # The table predates the Tier 1 / Tier 2 split, and
                    # CREATE TABLE IF NOT EXISTS is a no-op on an existing volume, so
                    # the second axis has to be added explicitly for anyone who
                    # already has crawl state.
                    cursor.execute(
                        "ALTER TABLE crawl_urls "
                        "ADD COLUMN IF NOT EXISTS page_status VARCHAR(30) NULL;"
                    )
                conn.commit()
                self._initialized = True
        except Exception as e:
            logger.warning("crawl_state_init_deferred", error=str(e))

    def get_cursor(self, source_name: str, discipline: str) -> Dict[str, Any]:
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT last_page, scroll_offset, exhausted FROM crawl_cursors WHERE source_name = %s AND discipline = %s;",
                        (source_name, discipline)
                    )
                    row = cursor.fetchone()
                    if row:
                        return {
                            "last_page": row["last_page"],
                            "scroll_offset": row["scroll_offset"],
                            "exhausted": bool(row["exhausted"])
                        }
        except Exception as e:
            logger.error("crawl_state_get_cursor_failed", error=str(e))
        return {"last_page": 1, "scroll_offset": 0, "exhausted": False}

    def update_cursor(self, source_name: str, discipline: str, last_page: int, scroll_offset: int = 0, exhausted: bool = False):
        if self.read_only:
            logger.info("crawl_state_write_suppressed", op="update_cursor",
                        source_name=source_name, discipline=discipline, last_page=last_page)
            return
        self._init_db()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawl_cursors (source_name, discipline, last_page, scroll_offset, exhausted, updated_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (source_name, discipline) DO UPDATE SET
                            last_page = EXCLUDED.last_page,
                            scroll_offset = EXCLUDED.scroll_offset,
                            exhausted = EXCLUDED.exhausted,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        (source_name, discipline, last_page, scroll_offset, exhausted)
                    )
                conn.commit()
        except Exception as e:
            logger.error("crawl_state_update_cursor_failed", error=str(e))

    def is_url_scraped(self, url: str) -> bool:
        """Has this program's structured row been ingested? (Tier 1 axis.)"""
        self._init_db()
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT status FROM crawl_urls WHERE url_hash = %s;", (url_hash,)
                    )
                    row = cursor.fetchone()
                    return bool(row and row["status"] == "scraped")
        except Exception as e:
            logger.error("crawl_state_is_url_scraped_failed", error=str(e))
            return False

    def is_page_fetched(self, url: str) -> bool:
        """Has this program's PAGE been fetched for the document corpus? (Tier 2 axis.)

        Two axes are required, not one. Tier 1 builds program_requirements from the
        search API's cards with no page fetch, and marks the URL scraped. If Tier 2
        reused that same flag it would skip every program Tier 1 had already covered —
        which is every program — and the document corpus would never grow.
        """
        self._init_db()
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT page_status FROM crawl_urls WHERE url_hash = %s;",
                        (url_hash,),
                    )
                    row = cursor.fetchone()
                    return bool(row and row["page_status"] == "fetched")
        except Exception as e:
            logger.error("crawl_state_is_page_fetched_failed", error=str(e))
            return False

    def mark_page_status(self, url: str, page_status: str,
                         error_message: Optional[str] = None):
        """Record the Tier 2 (page fetch) axis without disturbing the Tier 1 status."""
        if self.read_only:
            logger.info("crawl_state_write_suppressed", op="mark_page_status",
                        url=url, page_status=page_status)
            return
        self._init_db()
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawl_urls
                        SET page_status = %s,
                            error_message = COALESCE(%s, error_message),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE url_hash = %s;
                        """,
                        (page_status, error_message, url_hash),
                    )
                conn.commit()
        except Exception as e:
            logger.error("crawl_state_mark_page_status_failed", error=str(e))

    def mark_url_status(self, source_name: str, discipline: str, url: str, status: str, error_message: Optional[str] = None):
        if self.read_only:
            logger.info("crawl_state_write_suppressed", op="mark_url_status",
                        url=url, status=status)
            return
        self._init_db()
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawl_urls (url_hash, source_name, discipline, url, status, attempts, error_message, updated_at)
                        VALUES (%s, %s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (url_hash) DO UPDATE SET
                            status = EXCLUDED.status,
                            attempts = crawl_urls.attempts + 1,
                            error_message = EXCLUDED.error_message,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        (url_hash, source_name, discipline, url, status, error_message)
                    )
                conn.commit()
        except Exception as e:
            logger.error("crawl_state_mark_url_status_failed", error=str(e))

# Shared singleton
crawl_state = CrawlStateManager()
