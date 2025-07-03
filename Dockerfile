# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy all source code from the search_terms_cleaner folder into the container root
COPY search_terms_cleaner/ .

# Default command to run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

