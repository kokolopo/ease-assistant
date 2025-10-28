FROM python:3.12-slim

# Set environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install uv
RUN pip install --no-cache-dir uv

# Set workdir
WORKDIR /app

# Copy dependency file dan install dependencies
COPY pyproject.toml ./
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install -r requirements.txt --system
# Copy seluruh source code
COPY . .

# Expose port FastAPI
EXPOSE 1205

# Jalankan aplikasi
CMD ["fastapi", "run", "main.py", "--port", "1205"]
