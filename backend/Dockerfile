# ── Backend Dockerfile ────────────────────────────────────────────────────────
# Place this at: backend/Dockerfile

# Python 3.11 slim — small image, fast pulls
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies
# gcc is needed to compile some Python packages (numpy, etc.)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first — Docker caches this layer separately.
# If requirements.txt hasn't changed, this layer is reused on rebuild.
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend source files
COPY . .

# Create the data directory where SQLite DB will live
# This will be overridden by the volume mount in docker-compose,
# but it ensures the directory exists if running standalone
RUN mkdir -p data

# Expose the FastAPI port
EXPOSE 8000

# Start the FastAPI server
# --host 0.0.0.0 makes it reachable from outside the container
# --reload is OFF in production — remove it for faster startup
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
