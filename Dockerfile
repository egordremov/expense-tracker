FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --gid 10001 expense \
    && useradd --uid 10001 --gid expense --no-create-home expense \
    && install -d -m 700 -o expense -g expense /app/data
COPY *.py LICENSE ./
COPY static ./static
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DB_PATH=/app/data/expenses.db
VOLUME /app/data
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
