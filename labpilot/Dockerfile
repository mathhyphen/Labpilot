# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        sqlite3 \
        curl \
        bash \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Make the labrun script executable
RUN chmod +x labrun
RUN chmod +x notify.sh
RUN chmod +x git-snapshot.sh

# Expose port for the web interface
EXPOSE 8000

# Run the application
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8000"]