FROM python:3.10-slim

# Set working directory
WORKDIR /app/search_terms_cleaner

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev \
    && apt-get clean

# Install Python packages
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy source code
COPY . /app/search_terms_cleaner

# Run app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
