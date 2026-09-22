FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY symple ./symple
RUN pip install --no-cache-dir ".[web]"
ENV PORT=8765
EXPOSE 8765
CMD ["sh", "-c", "symple serve --host 0.0.0.0 --port ${PORT}"]
