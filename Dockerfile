# Stage 1: Download the model
# FIX: Capitalized 'AS' to fix the casing warning
FROM python:3.11-slim AS downloader
WORKDIR /models

# FIX: Install build tools needed for some python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

# FIX: Upgrade pip to prevent installation errors
RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir sentence-transformers
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5', cache_folder='.')"

# Stage 2: Build the final application
FROM python:3.11-slim
WORKDIR /code

# Set environment variables for caching
ENV SENTENCE_TRANSFORMERS_HOME=/code/models
ENV HF_HOME=/code/models

# FIX: Install system dependencies for the main app (needed for FAISS/numpy)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Create directories with permissions
RUN mkdir -p /code/data && chmod -R 777 /code/data

# Copy requirements and install dependencies
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the pre-downloaded model from the first stage
COPY --from=downloader /models /code/models

# Copy the application code and data
COPY ./app /code/app
COPY ./data /code/data

# FIX: Use JSON format for CMD to fix the OS signal warning
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]