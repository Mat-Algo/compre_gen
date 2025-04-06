FROM python:3.11-slim

# System + build dependencies for Manim, pycairo, LaTeX, and voiceover
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    python3-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libglib2.0-dev \
    ffmpeg \
    sox \
    libsox-fmt-all \
    gettext \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    dvipng \
    cm-super \
 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install all Python dependencies (including manim-voiceover)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "manim-voiceover[elevenlabs,transcribe]"

# Copy the rest of the code
COPY . .

# Setup video output directory
ENV VIDEO_DIR=/videos
RUN mkdir -p /videos

# Expose port
EXPOSE 5000

# Run the app with Gunicorn
CMD hypercorn app:app --bind 0.0.0.0:$PORT

