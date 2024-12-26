# Используем Python 3.11 в качестве базового образа
FROM python:3.11

# Устанавливаем зависимости для VPN
RUN apt-get update && \
    apt-get install -y \
    sstp-client \
    ppp \
    curl \
    wget \
    iproute2 \
    iputils-ping \
    ca-certificates \
    ffmpeg \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости Python
COPY requirements.txt .
COPY requirements-docker-app.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-docker-app.txt

# Копируем приложение
COPY . .

# Устанавливаем переменные окружения для VPN
ENV VPN_USERNAME=vpn
ENV VPN_PASSWORD=vpn
ENV PROXY_HOST=vpn271901051.opengw.net
ENV PROXY_PORT=995

# Создаем конфигурационный файл VPN на лету
RUN echo "pty \"sstpc --cert-warn --log-level 3 --ipcp-accept-local --ipcp-accept-remote --user $VPN_USERNAME --password $VPN_PASSWORD --ssl-verify --vpn-server $PROXY_HOST --port $PROXY_PORT\"" > /etc/ppp/peers/vpn_config && \
    echo "name $VPN_USERNAME" >> /etc/ppp/peers/vpn_config && \
    echo "remotename VPN" >> /etc/ppp/peers/vpn_config && \
    echo "require-mschap-v2" >> /etc/ppp/peers/vpn_config && \
    echo "file /etc/ppp/options" >> /etc/ppp/peers/vpn_config && \
    echo "$VPN_USERNAME * $VPN_PASSWORD *" > /etc/ppp/chap-secrets

# Команда для запуска VPN и приложения
CMD bash -c "pon vpn_config && python app.py"
