# Use an official Python base image (3.10 is safe for google-ads 24.0.0)
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy all project files into the container
COPY . /app

# Upgrade pip and install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose the port FastAPI will run on
EXPOSE 10000

# Start the FastAPI app with uvicorn (adjust path if needed)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "10000"]
