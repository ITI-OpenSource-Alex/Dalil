# Pin the community edition; `latest` may introduce auth/licensing changes.
FROM localstack/localstack:3.4.0

RUN set -eux; \
    for attempt in 1 2 3; do \
        apt-get update \
        && apt-get install -y --no-install-recommends ffmpeg \
        && rm -rf /var/lib/apt/lists/* \
        && break; \
        if [ "$attempt" -eq 3 ]; then exit 1; fi; \
        sleep 5; \
    done

COPY --chmod=755 init/ /etc/localstack/init/ready.d/
