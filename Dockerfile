FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
COPY examples ./examples

RUN pip install --no-cache-dir -e '.[api,postgres]'

RUN addgroup --system app && adduser --system --ingroup app app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

USER app

CMD ["uvicorn", "feme.api:app", "--host", "0.0.0.0", "--port", "8000"]
