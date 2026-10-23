FROM python:3.12.15-slim-bookworm
LABEL org.opencontainers.image.source="https://github.com/bmaged23/Fitness_multiagent_RAG"
WORKDIR /opt/fitness
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/fitness:/opt/fitness/src \
    SQLITE_DB_PATH=/opt/fitness/data/fitness_coach.db \
    EMBEDDING_MODEL=/opt/models/bge-large-en-v1.5 \
    ENABLE_SPEECH=false HF_HUB_OFFLINE=1 \
    OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/requirements-runtime.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt \
    && pip check
COPY docker/download_embedding.py /tmp/download_embedding.py
RUN HF_HUB_OFFLINE=0 python /tmp/download_embedding.py
COPY app ./app
COPY config ./config
COPY src ./src
COPY scripts/*.py ./scripts/
COPY db/*.sql ./db/
RUN useradd --uid 10001 --create-home fitness \
    && mkdir -p data && chown -R fitness:fitness data
USER fitness
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=3)"
CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
