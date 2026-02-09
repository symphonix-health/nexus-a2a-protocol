FROM python:3.11-slim

WORKDIR /app

COPY shared/command-centre/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared/command-centre/app /app/app
COPY shared/nexus_common /app/shared/nexus_common

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099"]
