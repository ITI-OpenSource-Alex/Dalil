#!/usr/bin/env bash
# GOA-036 — system-wide load test runner.
#
# Modelled on run-speaking-load.sh, which established the shape: snapshot
# Prometheus before, run k6 on the compose network, snapshot AFTER EVEN WHEN k6
# FAILS, and propagate k6's verdict only once every artefact is on disk. A run
# that crosses its thresholds is precisely the run whose metrics you want.
#
# It also does the thing that script's closing line handed to this ticket:
# uploads the evidence to S3 (LocalStack, for the same NO-AWS reason the metric
# backend is Prometheus rather than CloudWatch).
#
#   ./perf/run-load-test.sh                       # 10% scale, 10 minutes
#   LOAD_SCALE=0.2 LOAD_DURATION=5m ./perf/run-load-test.sh
#   LOAD_SCALE=1.0 ./perf/run-load-test.sh        # the ticket's full spec; costly
#
# Scale exists because the ticket rescoped itself by spend rather than by
# capability. See load-test.js for the arithmetic.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS="${REPO_ROOT}/perf/reports"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${REPORTS}"

LOAD_SCALE="${LOAD_SCALE:-0.1}"
LOAD_DURATION="${LOAD_DURATION:-10m}"
COMPOSE_NETWORK="${COMPOSE_NETWORK:-goa_default}"
GATEWAY_HOST="${GATEWAY_HOST:-http://localhost:8080}"
# Matches docker-compose.yml's own default (ADMIN_API_KEY:-local_admin_key_123).
# A wrong key here does not fail loudly -- /admin/costs just 401s and the spend
# snapshots land empty, which is how the first run produced two zero-byte cost
# files and no way to state what the run cost.
ADMIN_KEY="${ADMIN_API_KEY:-local_admin_key_123}"

# The pool must be at least as large as the WIDEST scenario, which is `match`
# at a fixed 50 VUs.
#
# Sharing identities is not a harmless economy: the Gateway allows 60 requests
# per user per minute, so N VUs behind one token get 60/N each. The first run of
# this harness used 3 tokens for 54 VUs and recorded 144,270 rate-limited
# requests out of 144,292 -- a 45-second measurement of the rate limiter, with a
# "match p95 = 34ms" that was the latency of being refused.
TOKEN_COUNT="${TOKEN_COUNT:-$(python -c "print(max(50, round(100*${LOAD_SCALE})))")}"

echo "== GOA-036 load test =="
echo "   scale=${LOAD_SCALE}  duration=${LOAD_DURATION}  tokens=${TOKEN_COUNT}"
echo

# --- Catalogue size -----------------------------------------------------------
# The ticket requires the report to say whether the run was bounded by spend or
# by catalogue size, so the catalogue is measured rather than assumed.
echo "== catalogue size =="
docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T postgres \
  psql -U goa -d rag_db -t -A -F',' -c \
  "SELECT
     (SELECT count(*) FROM program_requirements),
     (SELECT count(*) FROM program_requirements WHERE source_url NOT LIKE '%goa.internal%'),
     (SELECT count(*) FROM documents),
     (SELECT count(*) FROM visa_requirements);" \
  > "${REPORTS}/${STAMP}-catalogue.csv" 2>/dev/null \
  || echo "WARNING: could not read catalogue size" >&2
cat "${REPORTS}/${STAMP}-catalogue.csv" 2>/dev/null || true
echo

# --- Spend, before ------------------------------------------------------------
echo "== spend snapshot: before =="
curl -fsS -H "X-Admin-Key: ${ADMIN_KEY}" "${GATEWAY_HOST}/admin/costs" \
  > "${REPORTS}/${STAMP}-costs-before.json" 2>/dev/null \
  || echo "WARNING: /admin/costs unavailable (check ADMIN_API_KEY)" >&2

# --- Accounts -----------------------------------------------------------------
python "${REPO_ROOT}/perf/provision_load_users.py" \
  --gateway "${GATEWAY_HOST}" \
  --count "${TOKEN_COUNT}" \
  --out "${REPO_ROOT}/perf/tokens.json" \
  --meta-out "${REPORTS}/${STAMP}-tokens-meta.json"
if [[ ! -s "${REPO_ROOT}/perf/tokens.json" ]]; then
  echo "FATAL: no tokens provisioned" >&2
  exit 1
fi

# Let the per-user rate-limit window drain before measuring.
#
# Provisioning is not free of the limiter it is setting up for: each account
# spends a PUT /api/profile, two billing calls and one or more
# /api/opportunities/query polls waiting for replication -- all inside the
# Gateway's 60-requests-per-user-per-minute window. Starting k6 immediately
# means the first minute of the run is measuring a budget that setup already
# spent. Observed directly: a 60-second run recorded 162 rate-limited requests
# and zero essay evaluations, because every essay upload was refused.
#
# The window is one minute, so 65 seconds clears it with margin.
COOLDOWN="${COOLDOWN_SECONDS:-65}"
if [[ "${COOLDOWN}" -gt 0 ]]; then
  echo "== cooling down ${COOLDOWN}s so the rate-limit window resets =="
  sleep "${COOLDOWN}"
fi
echo

# --- Prometheus, before -------------------------------------------------------
echo "== prometheus snapshot: before =="
for svc in gateway:8080 rag:8084 speaking:8082 writing:8000 orchestration:8083; do
  name="${svc%%:*}"; port="${svc##*:}"
  curl -fsS "http://localhost:${port}/metrics" \
    > "${REPORTS}/${STAMP}-prometheus-${name}-before.txt" 2>/dev/null \
    || echo "   (${name} metrics unavailable)" >&2
done

# --- k6 -----------------------------------------------------------------------
echo
echo "== k6 =="
# MSYS_NO_PATHCONV stops Git Bash rewriting the container-side paths into
# Windows ones before docker sees them. This has silently produced a wrong
# experimental result in this repo before.
# Local compose is the default target; a deployed environment overrides these.
# Against staging the Gateway is a public ALB, so k6 needs no compose network --
# DOCKER_NETWORK=bridge -- and the URLs are https/wss.
K6_GATEWAY="${K6_GATEWAY:-http://gateway:8080}"
K6_GATEWAY_WS="${K6_GATEWAY_WS:-ws://gateway:8080}"
DOCKER_NETWORK="${DOCKER_NETWORK:-${COMPOSE_NETWORK}}"

# Prometheus remote-write only exists on the local stack. Pointing k6 at a
# compose hostname from a bridge-network container makes every flush fail and
# floods the run output, so the output is dropped unless a URL is supplied.
K6_OUTPUT_ARGS=()
if [[ -n "${K6_PROM_RW_URL:-}" ]]; then
  K6_OUTPUT_ARGS+=(--out experimental-prometheus-rw)
fi

# Staging's ALB presents a self-signed certificate
# (create_self_signed_alb_certificate = true). This flag is scoped to that run
# and must never be set against a real certificate -- it would hide exactly the
# TLS misconfiguration a load test ought to surface.
K6_TLS_ARGS=()
if [[ "${K6_INSECURE_TLS:-}" == "true" ]]; then
  K6_TLS_ARGS+=(--insecure-skip-tls-verify)
fi

MSYS_NO_PATHCONV=1 docker run --rm --network "${DOCKER_NETWORK}" \
  -v "${REPO_ROOT}/perf:/perf" \
  -e GATEWAY="${K6_GATEWAY}" \
  -e GATEWAY_WS="${K6_GATEWAY_WS}" \
  -e TOKENS_FILE="/perf/tokens.json" \
  -e LOAD_SCALE="${LOAD_SCALE}" \
  -e LOAD_DURATION="${LOAD_DURATION}" \
  -e AUDIO_SECONDS="${AUDIO_SECONDS:-8}" \
  -e SPEAKING_TURNS="${SPEAKING_TURNS:-2}" \
  -e K6_PROMETHEUS_RW_SERVER_URL="${K6_PROM_RW_URL:-}" \
  -e K6_PROMETHEUS_RW_TREND_STATS="p(50),p(95),p(99),max" \
  grafana/k6 run \
    "${K6_OUTPUT_ARGS[@]}" \
    "${K6_TLS_ARGS[@]}" \
    --summary-export="/perf/reports/${STAMP}-k6.json" \
    /perf/load-test.js
K6_STATUS=$?

# --- Prometheus, after --------------------------------------------------------
# Captured unconditionally. `set -e` was aborting run-speaking-load.sh before its
# after-snapshot and throwing away the evidence for every failing run; this
# script never used set -e for that reason.
echo
echo "== prometheus snapshot: after =="
for svc in gateway:8080 rag:8084 speaking:8082 writing:8000 orchestration:8083; do
  name="${svc%%:*}"; port="${svc##*:}"
  curl -fsS "http://localhost:${port}/metrics" \
    > "${REPORTS}/${STAMP}-prometheus-${name}-after.txt" 2>/dev/null || true
done

echo "== spend snapshot: after =="
curl -fsS -H "X-Admin-Key: ${ADMIN_KEY}" "${GATEWAY_HOST}/admin/costs" \
  > "${REPORTS}/${STAMP}-costs-after.json" 2>/dev/null || true

# --- Schema validation ---------------------------------------------------------
# Not a formatting check: it asserts every metric the report and the bottleneck
# analysis read is present. A scenario that silently stopped running omits its
# metric entirely, and the report would otherwise render a blank cell instead of
# failing.
echo
echo "== validate report schema =="
if ! python "${REPO_ROOT}/perf/validate_report.py" "${REPORTS}/${STAMP}-k6.json"; then
  echo "   WARNING: the k6 summary did not validate. The run still happened and" >&2
  echo "   the artefacts are on disk, but do not publish numbers from it without" >&2
  echo "   reading the failures above." >&2
fi

# --- Evidence to S3 -----------------------------------------------------------
echo
echo "== upload to S3 (LocalStack) =="
LOCALSTACK="${LOCALSTACK_CONTAINER:-goa-localstack-1}"
if docker ps --format '{{.Names}}' | grep -q "^${LOCALSTACK}$"; then
  MSYS_NO_PATHCONV=1 docker exec -i "${LOCALSTACK}" sh -c 'mkdir -p /tmp/goa-perf && rm -rf /tmp/goa-perf/*'
  for artefact in "${REPORTS}/${STAMP}"-*; do
    [[ -e "${artefact}" ]] || continue
    docker cp "${artefact}" "${LOCALSTACK}:/tmp/goa-perf/" >/dev/null 2>&1 || true
  done
  MSYS_NO_PATHCONV=1 docker exec -i "${LOCALSTACK}" \
    awslocal s3 cp /tmp/goa-perf/ "s3://goa-e2e-reports/perf/${STAMP}/" --recursive >/dev/null \
    && echo "   s3://goa-e2e-reports/perf/${STAMP}/" \
    || echo "   WARNING: upload failed; artefacts remain in perf/reports/" >&2
else
  echo "   LocalStack container ${LOCALSTACK} not running; skipped." >&2
fi

# Tokens are live credentials for throwaway accounts. They expire in an hour,
# but leaving them in the working tree invites a commit.
rm -f "${REPO_ROOT}/perf/tokens.json"

echo
echo "Wrote:"
ls -1 "${REPORTS}/${STAMP}"-* 2>/dev/null | sed 's/^/  /'
echo
echo "k6 exit status: ${K6_STATUS} (non-zero means a threshold was crossed --"
echo "  which for chat and essay is EXPECTED and documented in GOA-036-report.md)"
exit "${K6_STATUS}"
