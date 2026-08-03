"""GOA-024 — scholarship matcher: dedup, batching, bulk fetch, event shape.

The ticket's DoD names most of these directly (dedup skips already-notified pairs,
SQS batches of 10, N users + 1 scholarship => N events, same cycle twice => no
duplicates). The bulk-fetch test is the one the ticket does not ask for and matters
most: "score against all users with matching targetCountry" is the same fan-out that
made /match unusable at catalog scale, and this worker runs in a 5-minute Lambda.
"""

import datetime


from app.workers.scholarship_matcher import (
    DEADLINE_REMINDER_DAYS,
    MATCH_SCORE_THRESHOLD,
    SQS_BATCH_SIZE,
    _batch,
    publish_events,
    run_matcher,
    score_profile_against_scholarship,
)


class FakeLedger:
    """In-memory stand-in with the real primary-key semantics."""

    def __init__(self):
        self.sent = set()

    def already_sent(self, user_id, program_id, cycle_date, event_type="ScholarshipMatched"):
        return (user_id, program_id, cycle_date, event_type) in self.sent

    def record(self, user_id, program_id, cycle_date, event_type="ScholarshipMatched"):
        self.sent.add((user_id, program_id, cycle_date, event_type))


def _profile(uid="u1", ielts=7.5, gpa=3.8, level="Master"):
    return {"userId": uid, "ieltsScore": ielts, "gpa": gpa, "gpaScale": "4.0",
            "degreeLevel": level, "ects": 180, "workExperienceYears": 2,
            "extracurricularsScore": 50, "targetCountries": ["Germany"],
            "fieldOfStudy": "Computer Science"}


def _scholarship(sid="s1", country="Germany", min_ielts=6.5, min_gpa=3.0,
                 deadline=None, level="Master"):
    return {"id": sid, "name": "DAAD Scholarship", "provider": "DAAD",
            "country": country, "degree_level": level, "award_amount": "EUR 900/mo",
            "deadline": deadline, "citizenship_eligible": True,
            "min_ielts": min_ielts, "min_gpa": min_gpa}


def _wire(mocker, scholarships, profiles, ledger=None):
    m = "app.workers.scholarship_matcher"
    mocker.patch(f"{m}.fetch_updated_scholarships", return_value=scholarships)
    fetch_profiles = mocker.patch(f"{m}.fetch_profiles_for_country", return_value=profiles)
    publish = mocker.patch(f"{m}.publish_events", side_effect=lambda ev, **kw: len(ev))
    return fetch_profiles, publish, (ledger or FakeLedger())


# ------------------------------------------------------------------- scoring

def test_strong_profile_scores_above_threshold():
    assert score_profile_against_scholarship(_profile(), _scholarship()) > MATCH_SCORE_THRESHOLD


def test_shortfall_is_proportional_not_binary():
    """Missing IELTS by 0.5 must not be penalised like missing it by 2.0."""
    near = score_profile_against_scholarship(_profile(ielts=6.0), _scholarship(min_ielts=6.5))
    far = score_profile_against_scholarship(_profile(ielts=4.5), _scholarship(min_ielts=6.5))
    assert near > far


def test_missing_profile_value_is_penalised_not_treated_as_pass():
    known = score_profile_against_scholarship(_profile(ielts=7.5), _scholarship(min_ielts=6.5))
    unknown = score_profile_against_scholarship(_profile(ielts=None), _scholarship(min_ielts=6.5))
    assert unknown < known


def test_score_stays_in_range():
    for ielts in (None, 0.0, 4.0, 9.0):
        for gpa in (None, 0.0, 4.0):
            s = score_profile_against_scholarship(
                _profile(ielts=ielts, gpa=gpa), _scholarship(min_ielts=7.0, min_gpa=3.9)
            )
            assert 0.0 <= s <= 100.0


# ---------------------------------------------------------------- deduplication

def test_same_pair_not_published_twice_in_one_cycle(mocker):
    """DoD: same (userId, programId, cycle_date) even if the matcher runs twice."""
    _, publish, ledger = _wire(mocker, [_scholarship()], [_profile()])
    first = run_matcher(ledger=ledger)
    second = run_matcher(ledger=ledger)
    assert first["matches"] == 1
    assert second["matches"] == 0
    assert second["skipped_duplicates"] >= 1


def test_dedup_skips_already_notified_pairs(mocker):
    _, _, ledger = _wire(mocker, [_scholarship()], [_profile()])
    ledger.record("u1", "s1", datetime.date.today().isoformat())
    assert run_matcher(ledger=ledger)["matches"] == 0


def test_unreadable_ledger_fails_closed(mocker):
    """A ledger that cannot be read must suppress sending, not duplicate emails."""
    from app.workers.scholarship_matcher import NotificationLedger
    ledger = NotificationLedger(db_url="postgresql://invalid:0/nope")
    assert ledger.already_sent("u1", "s1", "2026-01-01") is True


# -------------------------------------------------------------------- batching

def test_batches_group_into_tens():
    batches = list(_batch(list(range(25)), SQS_BATCH_SIZE))
    assert [len(b) for b in batches] == [10, 10, 5]


def test_publish_without_queue_url_sends_nothing(mocker):
    mocker.patch.dict("os.environ", {}, clear=False)
    mocker.patch("os.getenv", return_value=None)
    assert publish_events([{"a": 1}]) == 0


# ------------------------------------------------------------- fan-out control

def test_profiles_fetched_once_per_country_not_per_scholarship(mocker):
    """The anti-regression guard. Ten scholarships in one country must cost ONE
    profile fetch — the /match fan-out lesson, in a 5-minute Lambda."""
    scholarships = [_scholarship(sid=f"s{i}") for i in range(10)]
    fetch_profiles, _, ledger = _wire(mocker, scholarships, [_profile()])
    run_matcher(ledger=ledger)
    assert fetch_profiles.call_count == 1


def test_five_users_one_scholarship_yields_five_events(mocker):
    """DoD: seed N users + 1 matching scholarship => N events."""
    profiles = [_profile(uid=f"u{i}") for i in range(5)]
    _, publish, ledger = _wire(mocker, [_scholarship()], profiles)
    counts = run_matcher(ledger=ledger)
    assert counts["matches"] == 5
    assert len(publish.call_args.args[0]) == 5


def test_weak_profiles_produce_no_events(mocker):
    weak = [_profile(uid=f"u{i}", ielts=4.0, gpa=1.5) for i in range(3)]
    _, _, ledger = _wire(mocker, [_scholarship(min_ielts=8.0, min_gpa=3.9)], weak)
    assert run_matcher(ledger=ledger)["matches"] == 0


# --------------------------------------------------------------- deadline path

def test_imminent_deadline_adds_a_reminder_event(mocker):
    soon = (datetime.date.today() + datetime.timedelta(days=DEADLINE_REMINDER_DAYS - 1)).isoformat()
    _, publish, ledger = _wire(mocker, [_scholarship(deadline=soon)], [_profile()])
    counts = run_matcher(ledger=ledger)
    kinds = {e["eventType"] for e in publish.call_args.args[0]}
    assert kinds == {"ScholarshipMatched", "DEADLINE_REMINDER"}
    assert counts["reminders"] == 1


def test_distant_deadline_adds_no_reminder(mocker):
    far = (datetime.date.today() + datetime.timedelta(days=120)).isoformat()
    _, publish, ledger = _wire(mocker, [_scholarship(deadline=far)], [_profile()])
    run_matcher(ledger=ledger)
    assert {e["eventType"] for e in publish.call_args.args[0]} == {"ScholarshipMatched"}


def test_unparseable_deadline_does_not_abort_the_run(mocker):
    _, _, ledger = _wire(mocker, [_scholarship(deadline="rolling")], [_profile()])
    assert run_matcher(ledger=ledger)["matches"] == 1


# ----------------------------------------------------------------- event shape

def test_event_carries_the_fields_the_notification_service_needs(mocker):
    _, publish, ledger = _wire(mocker, [_scholarship(deadline="2026-12-01")], [_profile()])
    run_matcher(ledger=ledger)
    event = publish.call_args.args[0][0]
    for key in ("eventType", "userId", "programId", "programName", "provider",
                "country", "deadline", "score", "cycleDate"):
        assert key in event, key


def test_scholarship_without_country_is_skipped(mocker):
    _, _, ledger = _wire(mocker, [_scholarship(country=None)], [_profile()])
    assert run_matcher(ledger=ledger)["matches"] == 0
