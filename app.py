import asyncio
import os
import sys
import json
import redis
from urllib.parse import urlparse
from quart import Quart, request
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from handlers import callbacks, ya_ocr, summary, gpt, admin, stt, neuro, qwen
from utils.StatsMiddleware import StatsMiddleware
from utils.BanMiddleware import BanMiddleware

app = Quart(__name__)
load_dotenv()

if os.getenv("MIGRATE"):
    redis_url = os.getenv("REDIS_URL_MIGRATE")
    url = urlparse(redis_url)

    r = redis.Redis(
        host=url.hostname,
        port=url.port,
        password=url.password if url.password else None,
        ssl=True if url.scheme == "rediss" else False
    )

db_dir = "db/"

async def load_json_to_redis():
    if not os.getenv("MIGRATE"):
        return

    if not os.path.exists(db_dir):
        print(f"Directory {db_dir} does not exist.")
        return

    for filename in os.listdir(db_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(db_dir, filename)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                with open(file_path, "r") as file:
                    content = file.read()
                    try:
                        data = json.loads(content)
                        r.set(filename, json.dumps(data))
                        print(f"Data from {filename} has been saved to Redis.")
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON from {filename}: {e}")
            else:
                print(f"File {filename} is empty or does not exist.")

@app.route("/")
async def index():
    return "Главная страница"

@app.route("/pre-deploy", methods=["POST"])
async def pre_deploy():
    if request.headers.get("X-Deploy-Token") != "migrate":
        return {"status": "error", "message": "Unauthorized"}, 401

    await load_json_to_redis()
    return {"status": "success", "message": "Data reloaded to Redis"}

async def main():
    if sys.version_info < (3, 10):
        print("python >= 3.10 needed")
        sys.exit(1)

    bot = Bot(token=os.getenv("TG_BOT_TOKEN"))
    dp = Dispatcher()

    dp.update.middleware(BanMiddleware(bot))
    dp.update.middleware(StatsMiddleware(bot))

    dp.include_routers(
        callbacks.router, ya_ocr.router, summary.router, gpt.router,
        admin.router, stt.router, neuro.router, qwen.router
    )

    await load_json_to_redis()
    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(dp.start_polling(bot, polling_timeout=50))
    await app.run_task(host="0.0.0.0", port=80)

if __name__ == "__main__":
    asyncio.run(main())
