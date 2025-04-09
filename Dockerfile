FROM public.ecr.aws/lambda/python:3.11

RUN yum update -y && \
    yum install -y \
        gcc \
        gcc-c++ \
        make \
        pkgconfig \
        cairo-devel \
        pango-devel \
        glib2-devel \
        ffmpeg \
        sox \
        sox-devel \
        texlive-base \
        texlive-latex-extra \
        texlive-collection-fontsrecommended \
        dvipng \
        cm-super && \
    yum clean all


WORKDIR /var/task

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "manim-voiceover[elevenlabs,transcribe]"


RUN pip install --no-cache-dir mangum


COPY . .


ENV VIDEO_DIR=/videos
RUN mkdir -p /videos


ENV PORT=5000

CMD ["app.handler"]
