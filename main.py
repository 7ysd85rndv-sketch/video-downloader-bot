import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Просто пришли ссылку на видео из TikTok или Instagram — "
        "я скачаю его без водяного знака и пришлю тебе."
    )

@dp.message(F.text)
async def download_video(message: types.Message):
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        await message.answer("Пришли нормальную ссылку, пожалуйста.")
        return

    status = await message.answer("⏳ Скачиваю...")

    try:
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if not os.path.exists(filename):
                for f in os.listdir(DOWNLOAD_DIR):
                    if info.get("id") in f:
                        filename = os.path.join(DOWNLOAD_DIR, f)
                        break

        if not os.path.exists(filename):
            await status.edit_text("❌ Не удалось скачать видео.")
            return

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        if size_mb > 49:
            await status.edit_text(f"❌ Видео слишком большое ({size_mb:.1f} МБ).")
            os.remove(filename)
            return

        video = FSInputFile(filename)
        await message.answer_video(
            video=video,
            caption="✅ Готово! Без водяного знака"
        )
        await status.delete()
        os.remove(filename)

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await status.edit_text(
            "❌ Не получилось скачать.\n\n"
            "Возможные причины:\n"
            "• Видео приватное\n"
            "• Instagram иногда блокирует\n"
            "• Ссылка неправильная\n\n"
            "Попробуй другую ссылку."
        )

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
