import asyncio, os, sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from handlers import callbacks, ya_ocr, summary, gpt, admin, stt, neuro, qwen, pm, gemimg, tts, shazam, sdxl, rephrase
from utils.StatsMiddleware import StatsMiddleware
from utils.BanMiddleware import BanMiddleware

if sys.platform != "win32":
    import uvloop  # type: ignore
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

async def main():
    if sys.version_info < (3, 10):
        print("python >= 3.10 needed")
        sys.exit(1)
        
    load_dotenv()
    bot = Bot(token=os.getenv("TG_BOT_TOKEN"),
              default=DefaultBotProperties(allow_sending_without_reply = True))
    dp = Dispatcher()

    dp.update.middleware(BanMiddleware(bot))
    dp.update.middleware(StatsMiddleware(bot)) 

    dp.include_routers(
        callbacks.router, ya_ocr.router, summary.router, gpt.router,
        admin.router, stt.router, neuro.router, qwen.router, pm.router, gemimg.router, tts.router,
        shazam.router, sdxl.router, rephrase.router
    )

    await bot.delete_webhook(drop_pending_updates=True)    
    await dp.start_polling(bot, polling_timeout=50)
    

if __name__ == "__main__":
    asyncio.run(main())
