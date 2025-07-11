FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for building wheels
RUN apt-get update && apt-get install -y \
    build-essential \
    libyaml-dev \
    python3-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy app source code (includes main.py and cleaner.py)
COPY . /app

# Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
