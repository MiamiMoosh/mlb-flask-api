# Use Playwright's official image with built-in Chromium
FROM mcr.microsoft.com/playwright/python:v1.41.0

# Set working directory
WORKDIR /app

# Copy project files into the container
COPY . /app

# Install dependencies
RUN pip install -r requirements.txt

# Install Playwright browsers inside the container at build time
RUN playwright install --with-deps

# Expose Flask app port
EXPOSE 5000

# Start Gunicorn
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "server:app"]
