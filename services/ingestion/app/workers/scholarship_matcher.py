"""GOA-024 — scholarship matcher: diff engine and notification trigger.

Runs daily. For each scholarship changed in the last cycle (and each one whose
deadline is now imminent), scores every user targeting that country and publishes a
ScholarshipMatched or DEADLINE_REMINDER event for the strong matches.

Two design rules carried in from earlier tickets, both load-bearing:

* **Bulk, not fan-out.** Profiles and scholarships are each fetched once per country
  through RAG's internal API, and scoring happens in memory. The ticket's wording —
  "run scoring against all users with matching targetCountry" — is the same shape that
  made /match unusable at catalog scale (two queries per program, ~40,000 round trips).
  With a 5-minute Lambda ceiling and a 1000-user target, a per-user round trip would
  not survive its own acceptance criteria.
* **Ingestion never reads RAG's tables.** Everything comes through the internal API,
  same as the visa and program paths.

Deduplication lives in ingestion_db (`notifications_sent`), because it is this
worker's own state — the same ownership rule that puts crawl state here rather than
in rag_db.
"""

import datetime
import hashlib
import json
import os

import structlog

from client import get_headers
from config import settings

logger = structlog.get_logger("ingestion_worker.scholarship_matcher")

# The ticket's threshold: only a strong match is worth an email.
MATCH_SCORE_THRESHOLD = 60.0

# A scholarship becomes "urgent" inside this window, independent of whether its row
# changed — an unchanged scholarship can still be about to close.
DEADLINE_REMINDER_DAYS = 14

# SQS SendMessageBatch accepts at most 10 entries per call. This is an API limit, not
# a tuning choice: exceeding it fails the whole batch.
SQS_BATCH_SIZE = 10


def _iso_today() -> str:
    return datetime.date.today().isoformat()


# ----------------------------------------------------------------- dedup storage

class NotificationLedger:
    """(user_id, program_id, cycle_date) pairs already notified.

    Idempotency is the point: the matcher must be safe to re-run inside the same day
    (retry, manual trigger, duplicate EventBridge delivery) without emailing anyone
    twice. The primary key does the work — a re-run inserts nothing new.
    """

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.getenv(
            "INGESTION_DATABASE_URL",
            "postgresql://goa:goa_pass@localhost:5432/ingestion_db",
        )
        self._initialized = False

    def _connect(self):
        import psycopg2
        return psycopg2.connect(self.db_url)

    def _init(self):
        if self._initialized:
            return
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS notifications_sent (
                            user_id     VARCHAR(64)  NOT NULL,
                            program_id  VARCHAR(64)  NOT NULL,
                            cycle_date  DATE         NOT NULL,
                            event_type  VARCHAR(40)  NOT NULL DEFAULT 'ScholarshipMatched',
                            created_at  TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (user_id, program_id, cycle_date, event_type)
                        );
                        """
                    )
                conn.commit()
            self._initialized = True
        except Exception as e:
            logger.warning("notifications_ledger_init_deferred", error=str(e))

    def already_sent(self, user_id: str, program_id: str, cycle_date: str,
                     event_type: str = "ScholarshipMatched") -> bool:
        self._init()
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM notifications_sent
                        WHERE user_id = %s AND program_id = %s
                          AND cycle_date = %s AND event_type = %s;
                        """,
                        (user_id, program_id, cycle_date, event_type),
                    )
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error("notifications_ledger_read_failed", error=str(e))
            # Fail closed: an unreadable ledger must not cause duplicate emails.
            return True

    def record(self, user_id: str, program_id: str, cycle_date: str,
               event_type: str = "ScholarshipMatched") -> None:
        self._init()
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO notifications_sent
                            (user_id, program_id, cycle_date, event_type)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (user_id, program_id, cycle_date, event_type),
                    )
                conn.commit()
        except Exception as e:
            logger.error("notifications_ledger_write_failed", error=str(e))


# ------------------------------------------------------------------ RAG readers

def fetch_updated_scholarships(since_hours: int = 24,
                               deadline_within_days: int = DEADLINE_REMINDER_DAYS) -> list[dict]:
    import requests

    url = f"{settings.rag_service_url}/internal/scholarship-programs/updated"
    response = requests.get(
        url,
        params={"since_hours": since_hours, "deadline_within_days": deadline_within_days},
        headers=get_headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("scholarships", [])


def fetch_profiles_for_country(country: str) -> list[dict]:
    import requests

    url = f"{settings.rag_service_url}/internal/profiles/by-country"
    response = requests.get(
        url, params={"country": country}, headers=get_headers(), timeout=20
    )
    response.raise_for_status()
    return response.json().get("profiles", [])


# --------------------------------------------------------------------- scoring

def score_profile_against_scholarship(profile: dict, scholarship: dict) -> float:
    """Deterministic 0-100 match score. No LLM call, by design.

    GOA-125 removed the Stage-3 boost from bulk ranking on cost grounds, and this
    worker is far more fan-out-prone than /match ever was: users x scholarships. A
    daily job that made one model call per pair would dominate the entire budget.
    """
    score = 100.0

    min_ielts = scholarship.get("min_ielts")
    if min_ielts is not None:
        ielts = profile.get("ieltsScore")
        if ielts is None:
            score -= 30.0
        elif ielts < min_ielts:
            # Proportional, not binary: 0.5 short is not the same as 2.0 short.
            score -= min(40.0, (min_ielts - ielts) * 20.0)

    min_gpa = scholarship.get("min_gpa")
    if min_gpa is not None:
        gpa = profile.get("gpa")
        if gpa is None:
            score -= 30.0
        elif gpa < min_gpa:
            score -= min(40.0, (min_gpa - gpa) * 20.0)

    required_level = scholarship.get("degree_level")
    if required_level and profile.get("degreeLevel") \
            and required_level.strip().lower() != profile["degreeLevel"].strip().lower():
        score -= 25.0

    return max(0.0, min(100.0, score))


# ------------------------------------------------------------------- publishing

def _batch(items: list, size: int = SQS_BATCH_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def publish_events(events: list[dict], queue_url: str | None = None) -> int:
    """Publish in batches of 10 (the SQS API maximum). Returns the number sent."""
    if not events:
        return 0

    queue_url = queue_url or os.getenv("NOTIFICATION_QUEUE_URL")
    if not queue_url:
        logger.warning("notification_queue_url_missing", events=len(events))
        return 0

    import boto3

    client = boto3.client("sqs", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
    sent = 0
    for chunk in _batch(events):
        entries = [
            {"Id": hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest()[:32],
             "MessageBody": json.dumps(e)}
            for e in chunk
        ]
        try:
            result = client.send_message_batch(QueueUrl=queue_url, Entries=entries)
            sent += len(result.get("Successful", []))
            for failure in result.get("Failed", []) or []:
                logger.error("sqs_batch_entry_failed", **failure)
        except Exception as e:
            # One bad batch must not lose the rest — same isolation rule the
            # ingestion dual-write uses.
            logger.error("sqs_batch_failed", error=str(e), batch_size=len(chunk))
    return sent


# ------------------------------------------------------------------ the matcher

def run_matcher(since_hours: int = 24, ledger: NotificationLedger | None = None,
                queue_url: str | None = None) -> dict:
    ledger = ledger or NotificationLedger()
    cycle_date = _iso_today()
    today = datetime.date.today()

    scholarships = fetch_updated_scholarships(since_hours=since_hours)
    profiles_by_country: dict[str, list[dict]] = {}
    events: list[dict] = []
    counts = {"scholarships": len(scholarships), "users_evaluated": 0,
              "matches": 0, "reminders": 0, "skipped_duplicates": 0}

    for scholarship in scholarships:
        country = scholarship.get("country")
        if not country:
            continue

        # One profile fetch per distinct country, not per scholarship.
        if country not in profiles_by_country:
            profiles_by_country[country] = fetch_profiles_for_country(country)
        profiles = profiles_by_country[country]

        deadline = scholarship.get("deadline")
        is_urgent = False
        if deadline:
            try:
                days_left = (datetime.date.fromisoformat(deadline) - today).days
                is_urgent = 0 <= days_left <= DEADLINE_REMINDER_DAYS
            except ValueError:
                logger.warning("unparseable_deadline", deadline=deadline)

        for profile in profiles:
            counts["users_evaluated"] += 1
            score = score_profile_against_scholarship(profile, scholarship)
            if score <= MATCH_SCORE_THRESHOLD:
                continue

            user_id, program_id = profile["userId"], scholarship["id"]
            for event_type in (["ScholarshipMatched"] + (["DEADLINE_REMINDER"] if is_urgent else [])):
                if ledger.already_sent(user_id, program_id, cycle_date, event_type):
                    counts["skipped_duplicates"] += 1
                    continue
                events.append({
                    "eventType": event_type,
                    "userId": user_id,
                    "programId": program_id,
                    "programName": scholarship.get("name"),
                    "provider": scholarship.get("provider"),
                    "country": country,
                    "deadline": deadline,
                    "score": round(score, 2),
                    "cycleDate": cycle_date,
                })
                ledger.record(user_id, program_id, cycle_date, event_type)
                counts["matches" if event_type == "ScholarshipMatched" else "reminders"] += 1

    counts["events_published"] = publish_events(events, queue_url=queue_url)
    logger.info("scholarship_matcher_complete", **counts)
    return counts


def handler(event=None, context=None) -> dict:
    """Lambda entry point (EventBridge daily at 08:00 UTC)."""
    since_hours = int((event or {}).get("since_hours", 24))
    return run_matcher(since_hours=since_hours)


if __name__ == "__main__":
    import sys
    summary = run_matcher()
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary.get("scholarships", 0) >= 0 else 1)
