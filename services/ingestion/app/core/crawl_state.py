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

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv(
            "INGESTION_DATABASE_URL",
            "postgresql://goa:goa_pass@localhost:5432/ingestion_db"
        )
        self._initialized = False

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
                            status VARCHAR(30) NOT NULL, -- 'pending', 'scraped', 'failed'
                            attempts INTEGER DEFAULT 0,
                            error_message TEXT,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
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

    def mark_url_status(self, source_name: str, discipline: str, url: str, status: str, error_message: Optional[str] = None):
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
