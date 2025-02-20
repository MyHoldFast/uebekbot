import asyncio, os, sys
#import logging
from quart import Quart # type: ignore
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from handlers import callbacks, ya_ocr, summary, gpt, admin, stt, neuro, qwen
from utils.StatsMiddleware import StatsMiddleware
from utils.BanMiddleware import BanMiddleware

app = Quart(__name__)

load_dotenv()

#log_file_path = 'app.log'
#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
#    logging.FileHandler(log_file_path),
#    logging.StreamHandler()
#])
#logger = logging.getLogger(__name__)

@app.route('/')
async def index():
    return "Главная страница"

async def main():
    if sys.version_info < (3, 10):
        print("python >= 3.10 needed")
        sys.exit(1)
    bot = Bot(token=os.getenv("TG_BOT_TOKEN"))
    dp = Dispatcher()

    dp.update.middleware(BanMiddleware(bot))
    dp.update.middleware(StatsMiddleware(bot)) 

    dp.include_router(callbacks.router)
    dp.include_routers(ya_ocr.router, summary.router, gpt.router, admin.router, stt.router, neuro.router, qwen.router)

    await bot.delete_webhook(drop_pending_updates=True)
    #logger.info("Бот успешно запущен!")
    asyncio.create_task(dp.start_polling(bot, polling_timeout=50))
    await app.run_task(host='0.0.0.0', port=80)

if __name__ == "__main__":
    asyncio.run(main())
