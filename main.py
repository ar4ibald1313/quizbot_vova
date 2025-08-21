# main.py (aiogram 3.x)
# Функции: распределение по командам с равномерным балансом,
# визуализация (dice.gif + картинки команд), админ-сброс через UI.
# Требует: aiogram==3.x, python-dotenv

import asyncio
import os
import random
import sqlite3
from contextlib import closing
from typing import List, Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# -------------------- Конфиг --------------------
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в .env")

# Можно перечислить несколько ID через запятую в .env
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}

DB_PATH = "teams.db"

# Визуальные ресурсы
ASSETS_DIR = "assets"
DICE_GIF = os.path.join(ASSETS_DIR, "dice.gif")

# Команды: (название, девиз, путь к картинке)
TEAMS = [
    ("Эльфы", "Вечность за нами, победа в нас!", os.path.join(ASSETS_DIR, "elves.jpg")),
    ("Орки", "Кто сильнее — тот правее!", os.path.join(ASSETS_DIR, "orcs.jpg")),
    ("Гномы", "Камень — крепость, сталь — наша песня!", os.path.join(ASSETS_DIR, "dwarves.jpg")),
    ("Полурослики", "Мал да удал, но удача велика!", os.path.join(ASSETS_DIR, "halfings.jpg")),  # по твоему имени
    ("Драконорожденные", "Огонь в крови — слава в делах!", os.path.join(ASSETS_DIR, "dragons.jpg")),
]

# -------------------- БД --------------------
def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            team_index INTEGER NOT NULL
        )
        """)
        conn.commit()

def get_player_team(user_id: int) -> Optional[int]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT team_index FROM players WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else None

def insert_player(user_id: int, username: str, full_name: str, team_index: int) -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO players (user_id, username, full_name, team_index) VALUES (?,?,?,?)",
            (user_id, username, full_name, team_index)
        )
        conn.commit()

def counts_by_team() -> List[int]:
    counts = [0] * 5
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT team_index, COUNT(*) FROM players GROUP BY team_index")
        for idx, cnt in c.fetchall():
            if 0 <= idx < 5:
                counts[idx] = cnt
    return counts

def reset_all():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM players")
        conn.commit()

# -------------------- Балансировщик --------------------
def pick_balanced_team() -> int:
    cnts = counts_by_team()
    mn = min(cnts)
    candidates = [i for i, c in enumerate(cnts) if c == mn]
    return random.choice(candidates)

# -------------------- UI --------------------
def main_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎲 Определи мою судьбу", callback_data="join")],
        [InlineKeyboardButton(text="📊 Моя команда", callback_data="myteam")],
    ]
    if user_id in ADMIN_IDS:
        rows.append([InlineKeyboardButton(text="⚠️ Сбросить", callback_data="admin_reset")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def confirm_reset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сбросить всё", callback_data="confirm_reset_yes")],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="confirm_reset_no")],
    ])

def team_caption(team_index: int) -> str:
    name, motto, _ = TEAMS[team_index]
    return f"<b>{name}</b>\n{motto}"

# -------------------- Бот --------------------
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(CommandStart())
async def on_start(message: types.Message):
    init_db()
    await message.answer(
        "Привет! Жми «🎲 Определи мою судьбу», и я распределю тебя в одну из 5 фэнтези-команд.",
        reply_markup=main_kb(message.from_user.id)
    )

@dp.message(Command("myteam"))
async def on_myteam_cmd(message: types.Message):
    init_db()
    team = get_player_team(message.from_user.id)
    if team is None:
        await message.answer("Ты ещё не распределён. Жми кнопку ниже.", reply_markup=main_kb(message.from_user.id))
    else:
        _, _, pic = TEAMS[team]
        if os.path.isfile(pic):
            await bot.send_photo(message.chat.id, FSInputFile(pic), caption=team_caption(team),
                                 reply_markup=main_kb(message.from_user.id))
        else:
            await message.answer(team_caption(team), reply_markup=main_kb(message.from_user.id))

@dp.callback_query(F.data == "admin_reset")
async def on_admin_reset(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("Только для админов.")
    await cb.message.edit_text("⚠️ Сбросит все распределения. Точно?", reply_markup=confirm_reset_kb())
    await cb.answer()

@dp.callback_query(F.data == "confirm_reset_no")
async def on_reset_cancel(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("Только для админов.")
    await cb.message.edit_text("Отменено.", reply_markup=main_kb(cb.from_user.id))
    await cb.answer()

@dp.callback_query(F.data == "confirm_reset_yes")
async def on_reset_yes(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("Только для админов.")
    reset_all()
    await cb.message.edit_text("Готово. Всё очищено.", reply_markup=main_kb(cb.from_user.id))
    await cb.answer("Сброс выполнен.")

@dp.callback_query(F.data == "myteam")
async def on_myteam_cb(cb: types.CallbackQuery):
    team = get_player_team(cb.from_user.id)
    if team is None:
        await cb.message.edit_text("Ты ещё не распределён. Жми кнопку ниже.", reply_markup=main_kb(cb.from_user.id))
    else:
        await cb.message.delete()
        _, _, pic = TEAMS[team]
        if os.path.isfile(pic):
            await bot.send_photo(cb.message.chat.id, FSInputFile(pic), caption=team_caption(team),
                                 reply_markup=main_kb(cb.from_user.id))
        else:
            await bot.send_message(cb.message.chat.id, team_caption(team), reply_markup=main_kb(cb.from_user.id))
    await cb.answer()

@dp.callback_query(F.data == "join")
async def on_join(cb: types.CallbackQuery):
    init_db()
    user_id = cb.from_user.id
    team_existing = get_player_team(user_id)
    await cb.answer()

    # 1) Анимация "кубик" — если файл есть
    if os.path.isfile(DICE_GIF):
        try:
            await bot.send_animation(cb.message.chat.id, FSInputFile(DICE_GIF), caption="🎲 Определяем твою судьбу…")
        except Exception:
            pass
        await asyncio.sleep(1.0)

    # 2) Если уже распределён — показать команду
    if team_existing is not None:
        _, _, pic = TEAMS[team_existing]
        if os.path.isfile(pic):
            await bot.send_photo(cb.message.chat.id, FSInputFile(pic), caption=team_caption(team_existing),
                                 reply_markup=main_kb(cb.from_user.id))
        else:
            await bot.send_message(cb.message.chat.id, team_caption(team_existing),
                                   reply_markup=main_kb(cb.from_user.id))
        return

    # 3) Баланс и сохранение
    team_idx = pick_balanced_team()
    insert_player(
        user_id=user_id,
        username=cb.from_user.username or "",
        full_name=(cb.from_user.full_name or "").strip(),
        team_index=team_idx
    )

    # 4) Показ результата
    _, _, pic = TEAMS[team_idx]
    if os.path.isfile(pic):
        await bot.send_photo(cb.message.chat.id, FSInputFile(pic), caption=team_caption(team_idx),
                             reply_markup=main_kb(cb.from_user.id))
    else:
        await bot.send_message(cb.message.chat.id, team_caption(team_idx), reply_markup=main_kb(cb.from_user.id))

# -------------------- Точка входа --------------------
async def main():
    print("Bot is running…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
