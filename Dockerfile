FROM python:3.11

# Копируем файлы зависимостей
COPY requirements.txt .
COPY requirements-docker-app.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-docker-app.txt

# Устанавливаем ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Копируем все файлы приложения
COPY . .

# Указываем команду для запуска приложения
CMD ["python", "app.py"]  # Замените app.py на имя вашего файла с кодом