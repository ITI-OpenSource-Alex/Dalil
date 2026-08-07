#!/usr/bin/env bash
# GOA-032 load-test runner.
#
# Mints a Gateway-signed token, runs the k6 scenario through the Gateway, and
# writes both the k6 summary and a Prometheus snapshot into perf/reports/ as
# before/after evidence.
#
#   ./perf/run-speaking-load.sh          # 50 VUs, 30s of audio each
#   VUS=10 AUDIO_SECONDS=10 ./perf/run-speaking-load.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS="${REPO_ROOT}/perf/reports"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${REPORTS}"

VUS="${VUS:-50}"
AUDIO_SECONDS="${AUDIO_SECONDS:-30}"
JWT_SECRET="${JWT_SECRET:-supersecret_dev_key}"
SPEAKING_METRICS="${SPEAKING_METRICS:-http://localhost:8082/metrics}"
COMPOSE_NETWORK="${COMPOSE_NETWORK:-goa_default}"

# A token signed with the Gateway's own secret. The load test must go through
# the real auth path -- bypassing it would measure a route that does not exist.
JWT="$(cd "${REPO_ROOT}/services/gateway" && JWT_SECRET="${JWT_SECRET}" go run ./cmd/mintjwt 2>/dev/null || true)"
if [[ -z "${JWT}" ]]; then
  echo "Could not mint a token. Set JWT=<access token> explicitly and re-run." >&2
  exit 1
fi

echo "== Prometheus snapshot: before =="
curl -fsS "${SPEAKING_METRICS}" > "${REPORTS}/${STAMP}-prometheus-before.txt"

echo "== k6: ${VUS} concurrent sessions, ${AUDIO_SECONDS}s of audio each =="
# MSYS_NO_PATHCONV stops Git Bash on Windows rewriting the container-side paths
# below into Windows ones before docker ever sees them.
MSYS_NO_PATHCONV=1 docker run --rm --network "${COMPOSE_NETWORK}" \
  -v "${REPO_ROOT}/perf:/perf" \
  -e GATEWAY_WS="ws://gateway:8080" \
  -e JWT="${JWT}" \
  -e VUS="${VUS}" \
  -e AUDIO_SECONDS="${AUDIO_SECONDS}" \
  grafana/k6 run /perf/speaking-load.js \
  --summary-export="/perf/reports/${STAMP}-k6.json" && K6_STATUS=0 || K6_STATUS=$?

# The after-snapshot is captured even when k6 exits non-zero. A run that crosses
# its thresholds is precisely the run whose Prometheus state you want to look
# at; `set -e` was aborting before the snapshot and throwing away the evidence
# for every failing run.
echo "== Prometheus snapshot: after =="
curl -fsS "${SPEAKING_METRICS}" > "${REPORTS}/${STAMP}-prometheus-after.txt"

echo
echo "Wrote:"
echo "  ${REPORTS}/${STAMP}-k6.json"
echo "  ${REPORTS}/${STAMP}-prometheus-before.txt"
echo "  ${REPORTS}/${STAMP}-prometheus-after.txt"
echo
echo "Upload to S3 is GOA-036's scope (it owns the CloudWatch/S3 evidence pipeline)."

# Propagate k6's verdict so CI or a caller can act on it, but only after every
# artefact is on disk.
exit "${K6_STATUS}"
