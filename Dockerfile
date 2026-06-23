FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy project files
COPY . .

# Convert Windows CRLF to LF for shell scripts
RUN if [ -f /app/start.sh ]; then sed -i 's/\r$//' /app/start.sh; fi \
    && chmod +x /app/start.sh

EXPOSE 8000

CMD ["./start.sh"]
