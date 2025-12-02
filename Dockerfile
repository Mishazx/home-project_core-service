FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Установим системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Копируем только зависимости для кеша и используем BuildKit cache для pip
# Требует buildx/BuildKit, но workflow использует buildx
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r /app/requirements.txt

# Код монтируется томом в dev. На проде можно раскомментировать COPY:
RUN mkdir -p /app/core_service
# Копируем весь репозиторий внутрь папки пакета, чтобы запуск через
# `python -m core_service.main` работал корректно (создаём package)
COPY . /app/core_service
RUN if [ ! -f /app/core_service/__init__.py ]; then touch /app/core_service/__init__.py; fi

EXPOSE 11000

ENV CORE_DISABLE_ORCHESTRATOR=1

CMD ["python", "-m", "core_service.main"]


