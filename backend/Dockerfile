FROM python:3.12-slim

ARG UID=1000
ARG GID=1000

# Устанавливаем системные пакеты
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя
RUN groupadd -g ${GID} appgroup \
    && useradd -m -u ${UID} -g appgroup appuser

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Передаем права пользователю
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
