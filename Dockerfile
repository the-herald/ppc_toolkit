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
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy all source code from the search_terms_cleaner folder into container
COPY search_terms_cleaner/ /app/search_terms_cleaner

# Default command to run the API from inside /app/search_terms_cleaner
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
