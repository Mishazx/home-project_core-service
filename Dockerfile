FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Установим системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Копируем только зависимости для кеша
COPY core_service/requirements.txt /app/core_service/requirements.txt
RUN pip install --no-cache-dir -r /app/core_service/requirements.txt

# Код монтируется томом в dev. На проде можно раскомментировать COPY:
# COPY core_service /app/core_service

EXPOSE 11000

ENV CORE_DISABLE_ORCHESTRATOR=1

CMD ["python", "-m", "core_service.main"]


