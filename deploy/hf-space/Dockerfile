# RCM Intelligence API on a Hugging Face Docker Space (free CPU tier: 2 vCPU, 16 GB RAM).
# Built from the folder that scripts/deploy_hf_space.py stages: backend/ (with the GGUF model),
# knowledge/ and scripts/. Everything the API needs at runtime is baked in at build time:
# embedding + reranker models, the RAG index and the synthetic SQLite database.

FROM python:3.11-slim

# libgomp: OpenMP runtime used by the prebuilt llama.cpp and FAISS wheels.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Spaces run containers as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# CPU-only PyTorch first (the default wheel bundles ~2 GB of CUDA libraries), then the rest.
COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --user torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --user -r backend/requirements.txt

COPY --chown=user . .
WORKDIR /home/user/app/backend

# Download the embedding and reranker models into the image, build the RAG index, and seed the
# synthetic database with the same as-of date as the Presenter's Guide figures.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" \
    && python ../scripts/ingest_knowledge.py \
    && python ../scripts/seed_database.py --reset --as-of 2026-10-06

# The container sees the host's CPU count, so pin llama.cpp to the Space's 2 vCPUs; more threads
# than cores makes generation much slower. Models are already cached, so never call the Hub.
ENV ENVIRONMENT=production \
    LLM_N_THREADS=2 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 7860
# --proxy-headers: the Space's proxy forwards the client IP, so rate limits apply per visitor.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
