import asyncio
import os
import logging
import base64
import hmac
import time
from quart import Quart, render_template_string, jsonify, request, make_response  # type: ignore
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import redis  # Импортируем aioredis
from urllib.parse import urlparse
from handlers import callbacks, ya_ocr, summary, gpt, admin, stt

app = Quart(__name__)
app.secret_key = os.getenv("SECRET_KEY", "bombomlanneurchi")

log_file_path = 'app.log'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler(log_file_path),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)

load_dotenv()
bot = Bot(token=os.getenv("TG_BOT_TOKEN"))
dp = Dispatcher()

dp.include_router(callbacks.router)
dp.include_routers(ya_ocr.router, summary.router, gpt.router, admin.router, stt.router)

PASSWORD = os.getenv("APP_PASSWORD", "1234")

# Глобальная переменная для Redis
redis_client = None

def create_token():
    expiration_time = int(time.time()) + 30 * 24 * 60 * 60  # Токен действителен 30 дней (1 месяц)
    token_data = f"{expiration_time}"
    token = base64.urlsafe_b64encode(token_data.encode()).decode()
    signature = hmac.new(app.secret_key.encode(), token.encode(), 'sha256').hexdigest()
    return f"{token}.{signature}"

def verify_token(token):
    try:
        token_data, signature = token.rsplit('.', 1)
        expected_signature = hmac.new(app.secret_key.encode(), token_data.encode(), 'sha256').hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            return False

        decoded_data = base64.urlsafe_b64decode(token_data).decode()
        expiration_time = int(decoded_data)
        if time.time() > expiration_time:
            return False

        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке токена: {e}")
        return False

@app.route('/')
async def index():
    token = request.cookies.get('auth_token')
    is_logged_in = verify_token(token) if token else False
    logs = read_logs() if is_logged_in else []
    return await render_template_string('''
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Мониторинг бота</title>
        <style>
            body {
                display: flex;
                justify-content: center;
                align-items: flex-start;
                background-color: #121212;
                color: #ffffff;
                font-family: Arial, sans-serif;
                overflow: auto;
            }

            .container {
                text-align: center;
                padding: 20px;
                border: 1px solid #444;
                border-radius: 10px;
                background-color: #1e1e1e;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
                max-width: 600px;
                width: 100%;
            }

            h1 {
                color: #ffffff;
                margin-bottom: 15px;
            }
            p {
                color: #cccccc;
                margin-bottom: 15px;
            }
            #logs {
                text-align: left;
                box-sizing: border-box;
                margin-top: 10px;
                max-height: 300px;
                overflow-y: auto;
                border: 1px solid #444;
                padding: 10px;
                background-color: #2a2a2a;
                border-radius: 5px;
                font-family: 'Courier New', Courier, monospace;
                font-size: 14px;
                color: #ffffff;
                display: none;
                word-wrap: break-word;
                word-break: break-all;
                overflow-wrap: break-word;
                white-space: normal;
            }
            a.uptime-button {
                display: inline-block;
                margin-top: 10px;
                padding: 8px 15px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background-color 0.3s;
                font-size: 14px;
            }
            a.uptime-button:hover {
                background-color: #0056b3;
            }
            a {
                display: inline-block;
                margin-top: 10px;
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background-color 0.3s;
            }
            a:hover {
                background-color: #0056b3;
            }
            .log-title {
                font-weight: bold;
                font-size: 1.2em;
                margin-bottom: 10px;
                color: #ffffff;
                text-align: left;
                text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
            }
            .scroll-button {
                display: none;
                margin-top: 10px;
                padding: 8px 15px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background-color 0.3s;
            }
            .scroll-button:hover {
                background-color: #0056b3;
            }
            .error, .warning, .info {
                padding: 8px;
                border-radius: 3px;
                margin: 5px 0;
                display: block;
                word-wrap: break-word;
                position: relative;
            }
            .error {
                color: white;
                background-color: red;
                max-width: 100%;
                box-sizing: border-box;
            }
            .warning {
                color: white;
                background-color: darkorange;
                max-width: 100%;
                box-sizing: border-box;
            }
            .info {
                color: black;
                background-color: lightblue;
                max-width: 100%;
                box-sizing: border-box;
            }
            .password-form {
                background-color: #1e1e1e;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .password-form input {
                padding: 10px;
                border: 1px solid #444;
                border-radius: 5px;
                width: calc(100% - 22px);
                margin-bottom: 10px;
                background-color: #2a2a2a;
                color: #ffffff;
                font-size: 16px;
            }
            .password-form button {
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                transition: background-color 0.3s;
                font-size: 16px;
            }
            .password-form button:hover {
                background-color: #0056b3;
            }
            @media (max-width: 600px) {
                .container {
                    max-width: 100%;
                    padding: 10px;
                }
                body {
                    padding: 0;
                }
            }
        </style>
        <script>
            let autoScroll = true;

            async function submitPassword(event) {
                event.preventDefault();
                const password = document.getElementById('password').value;

                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ password })
                });

                const result = await response.json();
                if (result.success) {
                    loadLogs();
                    document.getElementById('logs').style.display = 'block';
                    document.getElementById('redis-data').style.display = 'block';
                    document.getElementById('log-title').style.display = 'block';
                    document.getElementById('password-form').style.display = 'none';
                    document.querySelector('.scroll-button').style.display = 'inline-block';
                    setInterval(loadLogs, 1000);
                } else {
                    alert('Неверный пароль. Попробуйте снова.');
                }
            }

            async function loadLogs() {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsDiv = document.getElementById('logs');
                const previousScrollHeight = logsDiv.scrollHeight;

                logsDiv.innerHTML = data.logs.map(log => {
                    const logId = 'log-' + Math.random().toString(36).substr(2, 9); // Генерация уникального ID для каждого лога
                    let logClass;

                    if (log.includes('ERROR')) {
                        logClass = 'error';
                    } else if (log.includes('WARNING')) {
                        logClass = 'warning';
                    } else if (log.includes('INFO')) {
                        logClass = 'info';
                    } else {
                        logClass = 'info';
                    }

                    return `
                        <div id="${logId}" class="${logClass}" style="position: relative; padding: 10px; margin-bottom: 5px; border: 1px solid #444; border-radius: 5px;">
                            <button onclick="copyToClipboard('${logId}')" style="position: absolute; top: 5px; right: 5px; background: none; border: none; color: #007bff; cursor: pointer;">📝</button>
                            <span style="display: block; padding-right: 30px;">${log}</span>
                        </div>
                    `;
                }).join('');

                if (autoScroll) {
                    logsDiv.scrollTop = logsDiv.scrollHeight;
                } else {
                    const newScrollHeight = logsDiv.scrollHeight;
                    if (newScrollHeight > previousScrollHeight) {
                        logsDiv.scrollTop = newScrollHeight - previousScrollHeight;
                    }
                }
            }

            function toggleAutoScroll() {
                autoScroll = !autoScroll;
            }

            function scrollToBottom() {
                const logsDiv = document.getElementById('logs');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            }

            function copyToClipboard(logId) {
                const logText = document.getElementById(logId).querySelector('span').innerText; // Изменено здесь
                navigator.clipboard.writeText(logText).catch(err => {
                    console.error('Ошибка при копировании текста: ', err);
                });
            }

            document.addEventListener('DOMContentLoaded', function() {
                const logsDiv = document.getElementById('logs');
                logsDiv.addEventListener('scroll', function() {
                    const isScrolledToBottom = logsDiv.scrollHeight - logsDiv.clientHeight <= logsDiv.scrollTop + 1;
                    autoScroll = isScrolledToBottom;
                });

                if ({{ is_logged_in|tojson }}) {
                    loadLogs();
                    document.getElementById('logs').style.display = 'block';
                    document.getElementById('log-title').style.display = 'block';
                    document.querySelector('.scroll-button').style.display = 'inline-block';
                    setInterval(loadLogs, 1000);
                }
            });
        </script>
    </head>
    <body>
        <div class="container">
            <h1>UebekBot</h1>
            <p>Чтобы бот на render.com не выключался, добавьте адрес в сервис <a href="https://uptimerobot.com" target="_blank" class="uptime-button">UptimeRobot</a> для мониторинга каждые 5 минут.</p>
            <p>Адрес вашего бота: <span id="bot-url"></span></p>
            <p id = "redis-data" style="display: {{ 'block' if is_logged_in else 'none' }}"><a href="/redis-data" class="uptime-button">Показать данные из Redis</a></p> <!-- Ссылка на страницу Redis -->
            <div id="password-form" class="password-form" style="display: {{ 'none' if is_logged_in else 'block' }}">
                <div class="log-title">Введите пароль для доступа к логам:</div>
                <form onsubmit="submitPassword(event)">
                    <input type="password" id="password" required placeholder="Введите пароль">
                    <button type="submit">Войти</button>
                </form>
            </div>
            <div id="log-title" class="log-title" style="display: {{ 'block' if is_logged_in else 'none' }}">Логи:</div>
            <div id="logs" style="display: {{ 'block' if is_logged_in else 'none' }}"></div>
            <button class="scroll-button" onclick="scrollToBottom()" style="display: {{ 'inline-block' if is_logged_in else 'none' }}">Прокрутить вниз</button>
        </div>
        <script>
            document.getElementById('bot-url').textContent = window.location.href;
        </script>
    </body>
    </html>
    ''', is_logged_in=is_logged_in, logs=[log.strip() for log in logs])

def read_logs():
    try:
        with open(log_file_path, 'r') as log_file:
            return [log.strip() for log in log_file.readlines()]
    except Exception as e:
        logger.error(f"Ошибка при чтении логов: {e}")
        return []

@app.route('/login', methods=['POST'])
async def login():
    try:
        data = await request.get_json()
        logger.info(f"Login attempt with data: {data}")
        password = data.get('password')
        if password == PASSWORD:
            token = create_token()
            response = await make_response(jsonify(success=True))
            response.set_cookie('auth_token', token, httponly=True, max_age=2592000)
            return response
        logger.warning("Login failed: Incorrect password")
        return jsonify(success=False)
    except Exception as e:
        logger.error(f"Error in /login route: {e}")
        return jsonify(success=False), 500

@app.route('/logs')
async def get_logs():
    token = request.cookies.get('auth_token')
    if not token or not verify_token(token):
        return jsonify(logs=[])

    return jsonify(logs=read_logs())

@app.route('/redis-data')
async def redis_data():
    token = request.cookies.get('auth_token')  # Предполагаем, что токен передается в заголовках
    if not token or not verify_token(token):
        return "Unauthorized", 401  # Возвращаем статус 401, если авторизация не пройдена

    keys = redis_client.keys('*')  # Получаем все ключи
    data = {}
    for key in keys:
        value = redis_client.get(key)
        data[key.decode('utf-8', errors='ignore')] = value.decode('utf-8', errors='ignore') if value else None

    return await render_template_string('''
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <title>Данные из Redis</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #121212;
                color: #ffffff;
                padding: 20px;
                max-width: 800px;  /* Фиксированная ширина */
                margin: auto;  /* Центрирование страницы */
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                border: 1px solid #444;
                padding: 10px;
                text-align: left;
            }
            th {
                background-color: #1e1e1e;
            }
            a.back-link {
                display: inline-block;
                margin-top: 20px;
                padding: 10px 15px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background-color 0.3s;
            }
            a.back-link:hover {
                background-color: #0056b3;
            }
        </style>
    </head>
    <body>
        <h1>Данные из Redis</h1>
        <table>
            <thead>
                <tr>
                    <th>Ключ</th>
                    <th>Значение</th>
                </tr>
            </thead>
            <tbody>
                {% for key, value in data.items() %}
                <tr>
                    <td>{{ key }}</td>
                    <td>{{ value }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <a href="/" class="back-link">Назад</a>
    </body>
    </html>
    ''', data=data)

async def main():
    global redis_client
    redis_url = "redis://red-cqll6ig8fa8c73b3fs9g:6379"
    url = urlparse(redis_url)

    # Инициализация клиента Redis
    redis_client = redis.StrictRedis(
        host=url.hostname,
        port=url.port,
        password=url.password,
        db=0
    )  # Убедитесь, что URL соответствует вашему Redis серверу
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот успешно запущен!")
    asyncio.create_task(dp.start_polling(bot, polling_timeout=50))
    await app.run_task(host='0.0.0.0', port=80)

if __name__ == "__main__":
    asyncio.run(main())
