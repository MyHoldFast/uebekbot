FROM python:3.12

COPY requirements.txt .
COPY requirements-docker-app.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-docker-app.txt

RUN apt-get update && \
    apt-get install -y git git-lfs ffmpeg build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN git lfs install && \
    mkdir -p trained_models && \
    wget -O trained_models/lid.176.bin https://github.com/MyHoldFast/uebekbot/raw/main/trained_models/lid.176.bin

COPY . .

ENTRYPOINT ["sh", "-c", "python post_deploy.py & python app.py"]