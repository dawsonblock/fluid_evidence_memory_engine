FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
COPY examples ./examples
RUN pip install --no-cache-dir -e '.[api,postgres]'
EXPOSE 8000
CMD ["uvicorn", "feme.api:app", "--host", "0.0.0.0", "--port", "8000"]
