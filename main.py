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

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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

    if cursor.fetchone():
        cursor.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?, last_active = ?
            WHERE user_id = ?
            """,
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
        "🔗 Отправь ссылку на видео из TikTok или Instagram.\n\n"
        "Я постараюсь отправить тебе:\n"
        "🎬 видео\n"
        "🎵 музыку отдельным MP3-файлом"
    )


# =========================
# STATS
# =========================

@dp.message(Command("stats"))
async def stats(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    today = date.today().isoformat()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE DATE(joined_at) = ?",
        (today,)
    )
    new_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM downloads")
    total_downloads = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE DATE(created_at) = ?",
        (today,)
    )
    today_downloads = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE download_type = 'video'"
    )
    videos = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE download_type = 'music'"
    )
    music = cursor.fetchone()[0]

    await message.answer(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"🆕 Новых сегодня: <b>{new_users}</b>\n\n"
        f"📥 Скачиваний: <b>{total_downloads}</b>\n"
        f"📅 Сегодня: <b>{today_downloads}</b>\n\n"
        f"🎬 Видео: <b>{videos}</b>\n"
        f"🎵 Музыка: <b>{music}</b>",
        parse_mode="HTML"
    )


# =========================
# DOWNLOAD
# =========================

@dp.message(F.text)
async def download_media(message: types.Message):

    register_user(message.from_user)

    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        await message.answer(
            "🔗 Отправь ссылку на видео."
        )
        return

    status = await message.answer("⏳ Скачиваю видео и музыку...")

    video_file = None
    audio_file = None

    try:

        # ---------- VIDEO ----------

        video_opts = {
            "outtmpl": f"{DOWNLOAD_DIR}/%(id)s_video.%(ext)s",
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        with YoutubeDL(video_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_file = ydl.prepare_filename(info)

        if not os.path.exists(video_file):
            for f in os.listdir(DOWNLOAD_DIR):
                if info.get("id") in f and "_video" in f:
                    video_file = os.path.join(DOWNLOAD_DIR, f)
                    break

        if not video_file or not os.path.exists(video_file):
            await status.edit_text("❌ Не удалось скачать видео.")
            return

        # ---------- AUDIO ----------

        audio_opts = {
            "outtmpl": f"{DOWNLOAD_DIR}/%(id)s_music.%(ext)s",
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with YoutubeDL(audio_opts) as ydl:
            ydl.download([url])

        audio_file = os.path.join(
            DOWNLOAD_DIR,
            f"{info.get('id')}_music.mp3"
        )

        if not os.path.exists(audio_file):
            audio_file = None

        # ---------- SIZE CHECK ----------

        video_size = os.path.getsize(video_file) / (1024 * 1024)

        if video_size > 49:
            await status.edit_text(
                f"❌ Видео слишком большое: {video_size:.1f} МБ"
            )
            return

        # ---------- SEND VIDEO ----------

        await message.answer_document(
            document=FSInputFile(video_file),
            caption="🎬 Видео готово"
        )

        add_download(message.from_user.id, "video")

        # ---------- SEND MUSIC ----------

        if audio_file and os.path.exists(audio_file):

            audio_size = os.path.getsize(audio_file) / (1024 * 1024)

            if audio_size <= 49:
                await message.answer_document(
                    document=FSInputFile(audio_file),
                    caption="🎵 Музыка готова"
                )

                add_download(message.from_user.id, "music")

        await status.delete()

    except Exception as e:

        logging.error(f"Ошибка: {e}")

        await status.edit_text(
            "❌ Не получилось скачать.\n\n"
            "Попробуй другую ссылку."
        )

    finally:

        for file in (video_file, audio_file):

            if file and os.path.exists(file):

                try:
                    os.remove(file)
                except Exception:
                    pass


# =========================
# MAIN
# =========================

async def main():

    print("Бот запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
