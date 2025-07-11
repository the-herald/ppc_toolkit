FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for building wheels (important for PyYAML, grpcio, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libyaml-dev \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for caching
COPY search_terms_cleaner/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy all app source code
COPY search_terms_cleaner /app

# Launch the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
