FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Match the host environment used by the local workbench (2026-10-31).
RUN pip install --no-cache-dir fastapi==0.137.1 uvicorn==0.49.0 requests==2.34.2
COPY puzzlescript_interface/__init__.py ./puzzlescript_interface/
COPY puzzlescript_interface/api/ ./puzzlescript_interface/api/
RUN useradd --create-home backend
USER backend
CMD ["python", "-m", "puzzlescript_interface.api.main"]
