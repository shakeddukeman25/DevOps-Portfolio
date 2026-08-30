# ==================================================
# Stage 1: Builder
# Installs the Python dependencies separately.
# Build tools/files from this stage do not need to
# remain in the final runtime image.
# ==================================================
FROM python:3.12-slim AS builder
WORKDIR /app
# Copy requirements first to improve Docker layer caching.
# Dependencies are reinstalled only when this file changes.
COPY requirements.txt .
# Install dependencies into a separate location.
# --no-cache-dir avoids storing unnecessary pip cache.
RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    -r requirements.txt
# ==================================================
# Stage 2: Runtime
# This is the final image that actually runs the app.
# It contains only what is needed at runtime.
# ==================================================
FROM python:3.12-slim AS runtime
WORKDIR /app
# Copy only the installed Python packages
# from the builder stage.
COPY --from=builder /install /usr/local
# Copy the application files.
COPY app.py .
COPY templates ./templates
# Create a non-root user for better container security.
RUN useradd --create-home appuser
# Run the application as a regular user instead of root.
USER appuser
# Documents that the Flask application listens on port 5000.
EXPOSE 5000
# Start the Flask application.
CMD ["python", "app.py"]