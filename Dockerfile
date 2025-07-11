FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for building wheels
RUN apt-get update && apt-get install -y \
    build-essential \
    libyaml-dev \
    python3-dev

# Copy requirements and install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy app code
COPY . /app

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
