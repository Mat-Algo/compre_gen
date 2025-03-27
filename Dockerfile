FROM python:3.11-slim

# System + build dependencies for Manim, pycairo, and LaTeX.
RUN apt-get update && apt-get install -y \
      build-essential \
      pkg-config \
      python3-dev \
      libcairo2-dev \
      libpango1.0-dev \
      libglib2.0-dev \
      ffmpeg \
      texlive-latex-base \
      texlive-latex-extra \
      texlive-fonts-recommended \
      dvipng \
      cm-super \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV VIDEO_DIR=/videos
RUN mkdir -p /videos

EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:${PORT}", "app:app"]