FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN ls -la /app
RUN pip install --no-cache-dir fastapi uvicorn redis pydantic

EXPOSE 8000

CMD ["python", "app.py"]