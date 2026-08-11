#!/usr/bin/env bash
# GOA-030 — build every deployed service image and push it to ECR.
#
# ECR repositories are IMMUTABLE (GOA-022 N7), so a tag can be pushed exactly
# once. IMAGE_TAG is therefore a deliberate, bumpable value rather than
# "latest" -- if an image turns out to be wrong, bump the tag, re-apply
# Terraform so the task definitions point at the new one, and redeploy.
#
#   ./infra/build-and-push.sh build          # build locally only, no AWS
#   ./infra/build-and-push.sh push           # login, push, requires repos to exist
#   ./infra/build-and-push.sh all
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACCOUNT="${AWS_ACCOUNT_ID:-114403655381}"
REGION="${AWS_REGION:-eu-west-1}"
PREFIX="${NAME_PREFIX:-goa-staging}"
IMAGE_TAG="${IMAGE_TAG:-goa030-1}"
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# service:context:dockerfile
#
# Context is per-service and NOT guesswork: orchestration, writing, rag,
# ingestion and notification COPY from packages/ (shared security, pricing and
# contracts code), so they only build from the repo root. gateway, user, exam,
# speech and embeddings COPY relative paths and build from their own directory.
# Reading the wrong one produces "failed to calculate checksum ... not found".
SERVICES=(
  "gateway:services/gateway:services/gateway/Dockerfile"
  "user:services/user:services/user/Dockerfile"
  "orchestration:.:services/orchestration/Dockerfile"
  "speaking:services/speaking:services/speaking/Dockerfile"
  "writing:.:services/writing/Dockerfile"
  "rag:.:services/rag/Dockerfile"
  "exam:services/exam:services/exam/Dockerfile"
  "ingestion:.:services/ingestion/Dockerfile"
  "speech:services/speech:services/speech/Dockerfile"
  "embeddings:services/embeddings:services/embeddings/Dockerfile"
)

MODE="${1:-all}"
FAILED=()

build_one() {
  local name="$1" context="$2" dockerfile="$3"
  local local_tag="${PREFIX}-${name}:${IMAGE_TAG}"
  echo "=== build ${name} ==="
  # --platform is not optional: Fargate runs linux/amd64, and a silently-built
  # arm64 image fails at task start with an exec format error that reads as a
  # broken entrypoint.
  if docker build --platform linux/amd64 \
      -t "${local_tag}" \
      -f "${REPO_ROOT}/${dockerfile}" \
      "${REPO_ROOT}/${context}"; then
    echo "    ok ${local_tag}"
  else
    echo "    FAILED ${name}" >&2
    FAILED+=("${name}")
  fi
}

push_one() {
  local name="$1"
  local local_tag="${PREFIX}-${name}:${IMAGE_TAG}"
  local remote_tag="${REGISTRY}/${PREFIX}-${name}:${IMAGE_TAG}"
  echo "=== push ${name} ==="
  docker tag "${local_tag}" "${remote_tag}" || { FAILED+=("${name}"); return; }
  if docker push "${remote_tag}"; then
    echo "    ok ${remote_tag}"
  else
    echo "    FAILED push ${name}" >&2
    FAILED+=("${name}")
  fi
}

if [[ "${MODE}" == "build" || "${MODE}" == "all" ]]; then
  for entry in "${SERVICES[@]}"; do
    IFS=':' read -r name context dockerfile <<< "${entry}"
    build_one "${name}" "${context}" "${dockerfile}"
  done
fi

if [[ "${MODE}" == "push" || "${MODE}" == "all" ]]; then
  echo "=== ecr login ==="
  aws ecr get-login-password --region "${REGION}" \
    | docker login --username AWS --password-stdin "${REGISTRY}" \
    || { echo "ECR login failed" >&2; exit 1; }
  for entry in "${SERVICES[@]}"; do
    IFS=':' read -r name _ _ <<< "${entry}"
    push_one "${name}"
  done
fi

echo
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "FAILED: ${FAILED[*]}" >&2
  exit 1
fi
echo "all images ${MODE} ok at tag ${IMAGE_TAG}"
