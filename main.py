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

from PIL import Image, ImageDraw, ImageFilter

# -------------------- Настройки --------------------
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в .env")

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}

DB_PATH = "teams.db"
ASSETS_DIR = "assets"
LOGOS_DIR = "logos"

TEAMS = [
    ("Эльфы", "Вечность за нами, победа в нас!", (34, 139, 34), (240, 255, 240), "leaf"),
    ("Орки", "Кто сильнее — тот правее!", (56, 79, 36), (248, 231, 28), "tusk"),
    ("Гномы", "Камень — крепость, сталь — наша песня!", (70, 70, 90), (220, 220, 220), "hammer"),
    ("Драконорожденные", "Огонь в крови — слава в делах!", (128, 0, 0), (255, 215, 0), "dragon"),
    ("Полурослики", "Мал да удал, но удача велика!", (139, 115, 85), (255, 245, 225), "clover"),
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

# -------------------- Логика --------------------
def pick_balanced_team() -> int:
    cnts = counts_by_team()
    mn = min(cnts)
    candidates = [i for i, c in enumerate(cnts) if c == mn]
    return random.choice(candidates)

# -------------------- Логотипы --------------------
def ensure_dirs():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(LOGOS_DIR, exist_ok=True)

def draw_leaf(draw, cx, cy, r, color):
    draw.ellipse([cx - r, cy - r*0.6, cx + r, cy + r*0.6], fill=color)

def draw_tusk(draw, cx, cy, r, color):
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], start=20, end=160, fill=color)
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], start=200, end=340, fill=color)

def draw_hammer(draw, cx, cy, r, color):
    draw.rectangle([cx - r//2, cy - r//2, cx + r//2, cy + r//2], fill=color)
    draw.rectangle([cx - 6, cy + r//2, cx + 6, cy + int(r*1.4)], fill=color)

def draw_dragon(draw, cx, cy, r, color):
    draw.ellipse([cx - r//2, cy - r//2, cx + r//2, cy + r//2], fill=color)

def draw_clover(draw, cx, cy, r, color):
    draw.ellipse([cx - r, cy - r, cx, cy], fill=color)
    draw.ellipse([cx, cy - r, cx + r, cy], fill=color)
    draw.ellipse([cx - r//2, cy, cx + r//2, cy + r], fill=color)

def ensure_logos():
    ensure_dirs()
    for idx, (name, motto, bg, fg, emblem) in enumerate(TEAMS):
        out_path = os.path.join(LOGOS_DIR, f"team_{idx+1}.png")
        if os.path.isfile(out_path):
            continue
        img = Image.new("RGB", (400, 400), bg)
        draw = ImageDraw.Draw(img)
        if emblem == "leaf": draw_leaf(draw, 200, 200, 100, fg)
        elif emblem == "tusk": draw_tusk(draw, 200, 200, 100, fg)
        elif emblem == "hammer": draw_hammer(draw, 200, 200, 100, fg)
        elif emblem == "dragon": draw_dragon(draw, 200, 200, 100, fg)
        elif emblem == "clover": draw_clover(draw, 200, 200, 100, fg)
        img.save(out_path)

def get_logo_path(team_index: int) -> str:
    ensure_logos()
    return os.path.join(LOGOS_DIR, f"team_{team_index+1}.png")

# -------------------- UI --------------------
def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Определи мою судьбу", callback_data="join")],
        [InlineKeyboardButton(text="📊 Моя команда", callback_data="myteam")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="stats")]
    ])

def stats_text() -> str:
    cnts = counts_by_team()
    total = sum(cnts)
    lines = [f"Всего участников: {total}"]
    for i, (name, motto, *_rest) in enumerate(TEAMS):
        lines.append(f"{i+1}. {name}: {cnts[i]}")
    return "\n".join(lines)

def team_caption(team_index: int) -> str:
    name, motto, *_ = TEAMS[team_index]
    return f"<b>{name}</b>\n{motto}"

# -------------------- Бот --------------------
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(CommandStart())
async def on_start(message: types.Message):
    init_db()
    ensure_logos()
    await message.answer("Привет! Жми «🎲 Определи мою судьбу».", reply_markup=main_kb())

@dp.message(Command("stats"))
async def on_stats_cmd(message: types.Message):
    await message.answer(stats_text())

@dp.message(Command("myteam"))
async def on_myteam_cmd(message: types.Message):
    team = get_player_team(message.from_user.id)
    if team is None:
        await message.answer("Ты ещё не распределён.", reply_markup=main_kb())
    else:
        await bot.send_photo(message.chat.id, FSInputFile(get_logo_path(team)), caption=team_caption(team))

@dp.message(Command("reset"))
async def on_reset_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("Эта команда только для админов.")
    reset_all()
    await message.answer("Сбросил распределение.")

@dp.callback_query(F.data == "stats")
async def on_stats_cb(cb: types.CallbackQuery):
    await cb.message.edit_text(stats_text(), reply_markup=main_kb())
    await cb.answer()

@dp.callback_query(F.data == "myteam")
async def on_myteam_cb(cb: types.CallbackQuery):
    team = get_player_team(cb.from_user.id)
    if team is None:
        await cb.message.edit_text("Ты ещё не распределён.", reply_markup=main_kb())
    else:
        await cb.message.delete()
        await bot.send_photo(cb.message.chat.id, FSInputFile(get_logo_path(team)), caption=team_caption(team), reply_markup=main_kb())
    await cb.answer()

@dp.callback_query(F.data == "join")
async def on_join(cb: types.CallbackQuery):
    init_db()
    user_id = cb.from_user.id
    team_existing = get_player_team(user_id)
    await cb.answer()

    if team_existing is not None:
        await bot.send_photo(cb.message.chat.id, FSInputFile(get_logo_path(team_existing)), caption=team_caption(team_existing), reply_markup=main_kb())
        return

    team_idx = pick_balanced_team()
    insert_player(
        user_id=cb.from_user.id,
        username=cb.from_user.username or "",
        full_name=(cb.from_user.full_name or "").strip(),
        team_index=team_idx
    )

    await bot.send_photo(cb.message.chat.id, FSInputFile(get_logo_path(team_idx)), caption=team_caption(team_idx), reply_markup=main_kb())

async def main():
    ensure_dirs()
    ensure_logos()
    print("Bot is running…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
