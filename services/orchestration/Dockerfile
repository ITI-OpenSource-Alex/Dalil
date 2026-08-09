FROM python:3.11-alpine AS base

WORKDIR /app

RUN apk add --no-cache gcc musl-dev postgresql-dev libffi-dev g++

# Repo-root build context (GOA-034), so this stage can see packages/. The
# service's own files are addressed by their full path from here on.
COPY services/orchestration/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared security primitives, deliberately NOT under /app.
#
# The dev target mounts ./services/orchestration over /app, which would hide
# anything copied there: the package would exist in the image, vanish at run
# time, and the import would fail only under compose. Living outside the mount
# point and arriving via PYTHONPATH keeps dev and prod identical.
ENV PYTHONPATH=/opt/goa:/opt/goa-pricing
COPY packages/security/py /opt/goa
# GOA-135: the shared LLM price table, in its OWN root rather than merged into
# /opt/goa. docker-compose bind-mounts ./packages/security/py over /opt/goa for
# the dev target, and a bind mount hides whatever the image put there -- so a
# package COPYed into /opt/goa exists in the image and is invisible under
# compose. Separate root, separate mount, dev and prod identical.
COPY packages/pricing/py /opt/goa-pricing

# Dev target
FROM base AS dev
EXPOSE 8083
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083", "--reload"]

# Production target
FROM base AS prod
COPY services/orchestration/ .
EXPOSE 8083
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083"]
