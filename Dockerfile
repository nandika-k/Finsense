FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for some Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Strip BOM if present (file was created on Windows) and install deps
RUN pip install --no-cache-dir --upgrade pip && \
    sed -i 's/^\xef\xbb\xbf//' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# HF Spaces runs containers as user 1000 — set ownership
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# HF Spaces requires port 7860
EXPOSE 7860

CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "7860"]
