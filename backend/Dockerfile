FROM python:3.12-slim

ARG UID=1000
ARG GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        wireguard-tools \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g ${GID} appgroup \
    && useradd -m -u ${UID} -g appgroup appuser \
    && mkdir -p /home/appuser/.ssh \
    && chown appuser:appgroup /home/appuser/.ssh \
    && chmod 700 /home/appuser/.ssh

WORKDIR /app/backend

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/backend

ENV PYTHONPATH=/app:/app/backend

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
