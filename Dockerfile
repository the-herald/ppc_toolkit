# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app/search_terms_cleaner

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev \
    && apt-get clean

# Copy Python requirements
COPY requirements.txt /app/requirements.txt

# Install Python packages
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy source code
COPY search_terms_cleaner/ /app/search_terms_cleaner

# Copy secret file (Render secret mount will make this available)
COPY client_secret.json /app/search_terms_cleaner/client_secret.json

# Default command to run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
