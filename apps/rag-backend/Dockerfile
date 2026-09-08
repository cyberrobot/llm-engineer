FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY application.py config.py contracts.py domain.py infrastructure.py logging_config.py main.py migrations.py cluster_roles.sql migration_owner_role.sql auth_audit_role.sql security.py ./
COPY prompts ./prompts

RUN useradd --create-home --uid 10001 rag && chown -R rag:rag /app
USER rag

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health/ready', timeout=2)"

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
