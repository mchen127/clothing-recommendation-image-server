# Use the official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Copy application source code
COPY . .

# Expose the port
EXPOSE 5000

# Start the Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:create_app()"]