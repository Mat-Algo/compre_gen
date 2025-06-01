FROM python:3.10-slim   

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tar \
    xz-utils \
    gcc \
    g++ \
    pkg-config \
    libcairo2-dev \
    libpango1.0-dev \
    libglib2.0-dev \
    sox \
    gettext \
    git \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-latex-extra \
    cm-super \
    llvm \
    clang \
    libssl-dev \
    rustc \
    cargo \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Add precompiled ffmpeg binary
RUN curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
    | tar -xJ \
 && cp ffmpeg-*/ffmpeg /usr/local/bin/ffmpeg \
 && chmod +x /usr/local/bin/ffmpeg \
 && rm -rf ffmpeg-*

WORKDIR /var/task

# Install torch CPU directly first (avoiding conflicts)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy app code
COPY . .

# Expose port
EXPOSE 8080

# Start FastAPI app using gunicorn + uvicorn worker
CMD ["sh", "-c", "exec gunicorn app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8080} --timeout 300"]
