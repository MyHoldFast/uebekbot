import asyncio, os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from handlers import callbacks, ya_ocr, summary, gpt, admin, stt

async def main():
    load_dotenv()
    bot = Bot(token=os.getenv("TG_BOT_TOKEN"))

    dp = Dispatcher()

    dp.include_router(callbacks.router)
    dp.include_routers(ya_ocr.router, summary.router, gpt.router, admin.router, stt.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
