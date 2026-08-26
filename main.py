import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8326418387

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# DATABASE
# =========================

db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    joined_at TEXT,
    last_active TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    download_type TEXT,
    created_at TEXT
)
""")

db.commit()


def register_user(user: types.User):
    now = datetime.now().isoformat()

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,)
    )

    exists = cursor.fetchone()

    if exists:
        cursor.execute(
            "UPDATE users SET username = ?, first_name = ?, last_active = ? WHERE user_id = ?",
            (user.username, user.first_name, now, user.id)
        )
    else:
        cursor.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, joined_at, last_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user.id, user.username, user.first_name, now, now)
        )

    db.commit()


def add_download(user_id: int, download_type: str):
    cursor.execute(
        """
        INSERT INTO downloads
        (user_id, download_type, created_at)
        VALUES (?, ?, ?)
        """,
        (user_id, download_type, datetime.now().isoformat())
    )

    db.commit()


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: types.Message):
    register_user(message.from_user)

    await message.answer(
        "👋 Привет!\n\n"
        "🔗 Просто отправь ссылку на видео из TikTok или Instagram.\n"
        "Я скачаю его и отправлю тебе."
    )


# =========================
# STATISTICS
# =========================

@dp.message(Command("stats"))
async def stats(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    register_user(message.from_user)

    today = date.today().isoformat()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE DATE(joined_at) = ?",
        (today,)
    )
    new_users_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM downloads")
    total_downloads = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE DATE(created_at) = ?",
        (today,)
    )
    downloads_today = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE download_type = 'video'"
    )
    videos = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE download_type = 'music'"
    )
    music = cursor.fetchone()[0]

    await message.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🆕 Новых сегодня: <b>{new_users_today}</b>\n\n"
        f"📥 Всего скачиваний: <b>{total_downloads}</b>\n"
        f"📥 Скачиваний сегодня: <b>{downloads_today}</b>\n\n"
        f"🎬 Видео: <b>{videos}</b>\n"
        f"🎵 Музыка: <b>{music}</b>",
        parse_mode="HTML"
    )


# =========================
# DOWNLOAD VIDEO
# =========================

@dp.message(F.text)
async def download_video(message: types.Message):

    register_user(message.from_user)

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
            await status.edit_text(
                f"❌ Видео слишком большое ({size_mb:.1f} МБ)."
            )
            os.remove(filename)
            return

        video = FSInputFile(filename)

        await message.answer_video(
            video=video,
            caption="✅ Готово!"
        )

        add_download(message.from_user.id, "video")

        await status.delete()

        os.remove(filename)

    except Exception as e:

        logging.error(f"Ошибка: {e}")

        await status.edit_text(
            "❌ Не получилось скачать.\n\n"
            "Попробуй другую ссылку."
        )


# =========================
# MAIN
# =========================

async def main():

    print("Бот запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
