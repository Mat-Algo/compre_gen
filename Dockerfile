FROM python:3.11-slim

# System dependencies for Manim
RUN apt-get update && \
    apt-get install -y \
      ffmpeg \
      libcairo2 \
      libpango1.0-0 \
      libglib2.0-0 \
      texlive-latex-base \
      texlive-latex-extra \
      texlive-fonts-recommended \
      dvipng \
      cm-super && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV VIDEO_DIR=/videos

RUN mkdir -p /videos

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
