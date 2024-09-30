import asyncio
import os
#import logging
from quart import Quart # type: ignore
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from handlers import callbacks, ya_ocr, summary, gpt, admin, stt, neuro
from utils.StatsMiddleware import StatsMiddleware

app = Quart(__name__)

#log_file_path = 'app.log'
#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
#    logging.FileHandler(log_file_path),
#    logging.StreamHandler()
#])
#logger = logging.getLogger(__name__)

load_dotenv()
bot = Bot(token=os.getenv("TG_BOT_TOKEN"))
dp = Dispatcher()

dp.include_router(callbacks.router)
dp.include_routers(ya_ocr.router, summary.router, gpt.router, admin.router, stt.router, neuro.router)

@app.route('/')
async def index():
    return "Главная страница"

async def main():
    dp.update.middleware(StatsMiddleware((await bot.get_me()).username))
    await bot.delete_webhook(drop_pending_updates=True)
    #logger.info("Бот успешно запущен!")
    asyncio.create_task(dp.start_polling(bot, polling_timeout=50))
    await app.run_task(host='0.0.0.0', port=80)

if __name__ == "__main__":
    asyncio.run(main())
