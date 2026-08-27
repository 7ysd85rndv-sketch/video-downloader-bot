import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
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
    last_active TEXT,
    referred_by INTEGER DEFAULT NULL,
    referrals INTEGER DEFAULT 0
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

# Добавляем новые колонки, если база была создана старой версией
try:
    cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL")
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE users ADD COLUMN referrals INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass

db.commit()


def register_user(user: types.User, referred_by=None):
    now = datetime.now().isoformat()

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,)
    )

    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?, last_active = ?
            WHERE user_id = ?
            """,
            (
                user.username,
                user.first_name,
                now,
                user.id
            )
        )
    else:
        # Нельзя пригласить самого себя
        if referred_by == user.id:
            referred_by = None

        cursor.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, joined_at, last_active, referred_by, referrals)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                user.id,
                user.username,
                user.first_name,
                now,
                now,
                referred_by
            )
        )

        # Засчитываем реферала
        if referred_by:
            cursor.execute(
                """
                UPDATE users
                SET referrals = referrals + 1
                WHERE user_id = ?
                """,
                (referred_by,)
            )

    db.commit()


def add_download(user_id: int, download_type: str):
    cursor.execute(
        """
        INSERT INTO downloads
        (user_id, download_type, created_at)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            download_type,
            datetime.now().isoformat()
        )
    )
    db.commit()


# =========================
# USER MENU
# =========================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Скачать видео",
                    callback_data="download_video"
                ),
                InlineKeyboardButton(
                    text="🎵 Скачать музыку",
                    callback_data="download_music"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Пригласить друга",
                    callback_data="referral"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Помощь",
                    callback_data="help"
                )
            ]
        ]
    )


# =========================
# START + REFERRALS
# =========================

@dp.message(CommandStart())
async def start(message: types.Message):

    referred_by = None

    # Получаем параметр из /start
    args = message.text.split(maxsplit=1)

    if len(args) > 1:
        referral_code = args[1]

        if referral_code.startswith("ref_"):
            try:
                referred_by = int(
                    referral_code.replace("ref_", "")
                )
            except ValueError:
                referred_by = None

    # Регистрируем пользователя
    register_user(
        message.from_user,
        referred_by
    )

    # Получаем количество приглашённых
    cursor.execute(
        "SELECT referrals FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )

    result = cursor.fetchone()
    referrals = result[0] if result else 0

    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я помогу скачать видео и музыку из "
        "TikTok, Instagram и Pinterest.\n\n"
        "🔗 Просто отправь мне ссылку.\n\n"
        f"👥 Ты пригласил друзей: <b>{referrals}</b>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


# =========================
# REFERRAL BUTTON
# =========================

@dp.callback_query(F.data == "referral")
async def referral(callback: types.CallbackQuery):

    await callback.answer()

    user_id = callback.from_user.id

    cursor.execute(
        "SELECT referrals FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cursor.fetchone()
    referrals = result[0] if result else 0

    referral_link = (
        f"https://t.me/topsavevideobot?start=ref_{user_id}"
    )

    share_url = (
        "https://t.me/share/url"
        f"?url={referral_link}"
        "&text=Попробуй этого бота для скачивания видео из TikTok, Instagram и Pinterest 👇"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Поделиться ботом",
                    url=share_url
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back_menu"
                )
            ]
        ]
    )

    await callback.message.answer(
        "👥 <b>Приглашай друзей</b>\n\n"
        "Отправь другу свою ссылку. "
        "Если он впервые запустит бота по ней — "
        "он будет засчитан как твой реферал.\n\n"
        f"🔗 <code>{referral_link}</code>\n\n"
        f"👥 Приглашено: <b>{referrals}</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# =========================
# BACK MENU
# =========================

@dp.callback_query(F.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):

    await callback.answer()

    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


# =========================
# BUTTONS
# =========================

@dp.callback_query(F.data == "download_video")
async def button_video(callback: types.CallbackQuery):

    await callback.answer()

    await callback.message.answer(
        "🎬 <b>Скачать видео</b>\n\n"
        "Отправь мне ссылку на видео.",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "download_music")
async def button_music(callback: types.CallbackQuery):

    await callback.answer()

    await callback.message.answer(
        "🎵 <b>Скачать музыку</b>\n\n"
        "Отправь ссылку — я отправлю аудио отдельным файлом.",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "help")
async def button_help(callback: types.CallbackQuery):

    await callback.answer()

    await callback.message.answer(
        "ℹ️ <b>Как пользоваться</b>\n\n"
        "1️⃣ Скопируй ссылку на видео\n"
        "2️⃣ Отправь её мне\n"
        "3️⃣ Подожди обработку\n"
        "4️⃣ Получи видео и музыку отдельными файлами",
        parse_mode="HTML"
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

    cursor.execute(
        "SELECT SUM(referrals) FROM users"
    )
    total_referrals = cursor.fetchone()[0] or 0

    await message.answer(
        "📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"🆕 Новых сегодня: <b>{new_users}</b>\n"
        f"👥 Рефералов: <b>{total_referrals}</b>\n\n"
        f"📥 Всего скачиваний: <b>{total_downloads}</b>\n"
        f"📅 Сегодня: <b>{today_downloads}</b>\n\n"
        f"🎬 Видео: <b>{videos}</b>\n"
        f"🎵 Музыка: <b>{music}</b>",
        parse_mode="HTML"
    )


# =========================
# ADMIN PANEL
# =========================

@dp.message(Command("admin"))
async def admin(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Пользователи",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Топ рефералов",
                    callback_data="top_referrals"
                )
            ]
        ]
    )

    await message.answer(
        "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "Выбери действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Доступ запрещён.",
            show_alert=True
        )
        return

    await callback.answer()

    today = date.today().isoformat()

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM downloads")
    downloads = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM downloads WHERE DATE(created_at) = ?",
        (today,)
    )
    today_downloads = cursor.fetchone()[0]

    cursor.execute(
        "SELECT SUM(referrals) FROM users"
    )
    referrals = cursor.fetchone()[0] or 0

    await callback.message.answer(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователи: <b>{users}</b>\n"
        f"📥 Скачивания: <b>{downloads}</b>\n"
        f"📅 Сегодня: <b>{today_downloads}</b>\n"
        f"👥 Рефералы: <b>{referrals}</b>",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Доступ запрещён.",
            show_alert=True
        )
        return

    await callback.answer()

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    await callback.message.answer(
        f"👥 Всего зарегистрированных пользователей: <b>{users}</b>",
        parse_mode="HTML"
    )


# =========================
# TOP REFERRALS
# =========================

@dp.callback_query(F.data == "top_referrals")
async def top_referrals(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Доступ запрещён.",
            show_alert=True
        )
        return

    await callback.answer()

    cursor.execute("""
        SELECT first_name, username, referrals
        FROM users
        WHERE referrals > 0
        ORDER BY referrals DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer(
            "🏆 Пока никто не пригласил пользователей."
        )
        return

    text = "🏆 <b>ТОП РЕФЕРАЛОВ</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, row in enumerate(rows):
        first_name, username, referrals = row

        name = first_name or "Без имени"

        if username:
            name += f" (@{username})"

        medal = medals[i] if i < 3 else f"{i + 1}."

        text += (
            f"{medal} {name} — "
            f"<b>{referrals}</b> приглашённых\n"
        )

    await callback.message.answer(
        text,
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

    status = await message.answer(
        "⏳ <b>Обрабатываю ссылку...</b>",
        parse_mode="HTML"
    )

    video_file = None
    audio_file = None
    video_id = None

    try:

        # =========================
        # VIDEO
        # =========================

        video_opts = {
            "outtmpl": f"{DOWNLOAD_DIR}/%(id)s_video.%(ext)s",
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        with YoutubeDL(video_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            video_id = info.get("id")

            video_file = ydl.prepare_filename(info)

        if not os.path.exists(video_file):

            for f in os.listdir(DOWNLOAD_DIR):

                if video_id and video_id in f and "_video" in f:

                    video_file = os.path.join(
                        DOWNLOAD_DIR,
                        f
                    )

                    break

        if not video_file or not os.path.exists(video_file):

            await status.edit_text(
                "❌ Не удалось скачать видео."
            )

            return

        # =========================
        # AUDIO MP3
        # =========================

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
            f"{video_id}_music.mp3"
        )

        # =========================
        # SEND VIDEO
        # =========================

        video_size = (
            os.path.getsize(video_file)
            / (1024 * 1024)
        )

        if video_size <= 49:

            await message.answer_document(
                document=FSInputFile(video_file),
                caption="🎬 <b>Видео готово</b>",
                parse_mode="HTML"
            )

            add_download(
                message.from_user.id,
                "video"
            )

        else:

            await message.answer(
                f"❌ Видео слишком большое: "
                f"{video_size:.1f} МБ"
            )

        # =========================
        # SEND MUSIC
        # =========================

        if os.path.exists(audio_file):

            audio_size = (
                os.path.getsize(audio_file)
                / (1024 * 1024)
            )

            if audio_size <= 49:

                await message.answer_document(
                    document=FSInputFile(audio_file),
                    caption="🎵 <b>Музыка готова</b>",
                    parse_mode="HTML"
                )

                add_download(
                    message.from_user.id,
                    "music"
                )

        await status.delete()

    except Exception as e:

        logging.error(
            f"Ошибка: {e}"
        )

        try:

            await status.edit_text(
                "❌ Не удалось обработать ссылку.\n\n"
                "Попробуй другую ссылку."
            )

        except Exception:
            pass

    finally:

        for file in (
            video_file,
            audio_file
        ):

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
