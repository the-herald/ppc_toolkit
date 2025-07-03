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

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy source code
COPY search_terms_cleaner/ /app/search_terms_cleaner

# Default command to run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
