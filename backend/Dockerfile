FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.dev

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir -p /data/evidence && chown -R app /data
USER app

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3 --timeout 60"]
