FROM python:3.11


COPY requirements.txt .
COPY requirements-docker-app.txt .


RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-docker-app.txt


RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*


COPY . .

ENTRYPOINT ["sh", "-c", "python post_deploy.py & python app.py"]