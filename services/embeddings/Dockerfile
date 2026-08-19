# GOA-030 — the embeddings sidecar.
#
# RAG embeds every query through an OpenAI-compatible endpoint. Locally that is
# an Ollama server on the developer's own machine, reached at
# host.docker.internal:11434 and deliberately NOT a compose service. Nothing
# equivalent existed in a deployed environment, so RAG fell back to that address
# inside a Fargate task, and every /query and /match failed at the embedding
# call -- quietly, with the real cause visible only in the RAG container's logs.
#
# Why Ollama with this exact model, rather than a hosted embedding API:
#
#   The catalogue already in the database was embedded with nomic-embed-text at
#   768 dimensions. Embeddings from different models do not share a vector
#   space, so pointing staging at (say) OpenAI's text-embedding-3-small would
#   not degrade quality -- it would make every similarity score meaningless,
#   while still returning plausible-looking numbers. Nothing would error. That
#   is the worst failure mode available, so the deployed sidecar serves the same
#   model the corpus was built with.
#
#   Changing the model is legitimate, but it is a re-embed of the whole corpus,
#   not a configuration change.
#
# The model is baked into the image rather than pulled at boot. A runtime pull
# needs egress, adds ~30s to every cold start, and turns a Hugging Face outage
# into a failure of our own service.
FROM ollama/ollama:0.5.7

# `ollama pull` needs a running server, so start one, pull, and stop it -- all
# within the single build layer, so the weights land in the image.
RUN ollama serve & \
    server=$! && \
    until ollama list >/dev/null 2>&1; do sleep 1; done && \
    ollama pull nomic-embed-text && \
    kill $server && \
    wait $server 2>/dev/null || true

# Bind to every interface: the default is loopback, which inside a Fargate task
# means the service is reachable by nothing, including its own health check.
ENV OLLAMA_HOST=0.0.0.0:11434
# One model, small, and the only caller is RAG. Keeping it resident avoids
# paying the load cost on the first query after an idle period, which would
# otherwise show up as an unexplained latency spike in the load test.
ENV OLLAMA_KEEP_ALIVE=-1

EXPOSE 11434

# The base image's ENTRYPOINT is ["/bin/ollama"], so CMD supplies the verb.
CMD ["serve"]
