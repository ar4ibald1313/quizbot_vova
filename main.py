import asyncio
import os
import random
import sqlite3
import time
from contextlib import closing
from typing import List, Optional, Tuple

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from dotenv import load_dotenv

# === Генерация логотипов (Pillow) ===
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------- Конфиг ----------
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в .env")

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}

DB_PATH = "teams.db"
ASSETS_DIR = "assets"
LOGOS_DIR = "logos"

# 5 команд: (имя, девиз, цвет фона, цвет эмблемы, тип эмблемы)
TEAMS = [
    ("Эльфы", "Вечность за нами, победа в нас!", (34, 139, 34), (240, 255, 240), "leaf"),
    ("Орки", "Кто сильнее — тот правее!", (56, 79, 36), (248, 231, 28), "tusk"),
    ("Гномы", "Камень — крепость, сталь — наша песня!", (70, 70, 90), (220, 220, 220), "hammer"),
    ("Драконорожденные", "Огонь в крови — слава в делах!", (128, 0, 0), (255, 215, 0), "dragon"),
    ("Полурослики", "Мал да удал, но удача велика!", (139, 115, 85), (255, 245, 225), "clover"),
]

# ---------- БД ----------
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

# ---------- Балансировщик ----------
def pick_balanced_team() -> int:
    cnts = counts_by_team()
    mn = min(cnts)
    candidates = [i for i, c in enumerate(cnts) if c == mn]
    return random.choice(candidates)

# ---------- Утилиты файлов ----------
def ensure_dirs():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(LOGOS_DIR, exist_ok=True)

def file_if_exists(*paths) -> Optional[str]:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None

# ---------- Генерация логотипов ----------
def draw_leaf(draw: ImageDraw.ImageDraw, cx, cy, r, color):
    # простая «эльфийская» листва — два эллипса
    draw.ellipse([cx - r, cy - r*0.6, cx + r, cy + r*0.6], fill=color)
    draw.line([cx, cy - r*0.6, cx, cy + r*0.6], fill=(0, 0, 0, 80), width=3)

def draw_tusk(draw: ImageDraw.ImageDraw, cx, cy, r, color):
    # пара клыков
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], start=20, end=160, fill=color)
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], start=200, end=340, fill=color)

def draw_hammer(draw: ImageDraw.ImageDraw, cx, cy, r, color):
    # молот + рукоять
    head_w, head_h = int(r*1.4), int(r*0.6)
    draw.rounded_rectangle(

[cx - head_w//2, cy - head_h//2, cx + head_w//2, cy + head_h//2],
        radius=10, fill=color
    )
    draw.rectangle([cx - 6, cy + head_h//2, cx + 6, cy + int(r*1.4)], fill=color)

def draw_dragon(draw: ImageDraw.ImageDraw, cx, cy, r, color):
    # минималистичный «дракон»: голова + крыло
    wing = [(cx - r, cy), (cx + r, cy - r//2), (cx + r//4, cy + r//3)]
    draw.polygon(wing, fill=color)
    draw.ellipse([cx - r//2, cy - r//2, cx + r//6, cy + r//6], fill=color)

def draw_clover(draw: ImageDraw.ImageDraw, cx, cy, r, color):
    # трилистник
    for a in (0, 120, 240):
        dx = int(r * 0.6 * round(__import__("math").cos(__import__("math").radians(a)), 6))
        dy = int(r * 0.6 * round(__import__("math").sin(__import__("math").radians(a)), 6))
        draw.ellipse([cx + dx - r//2, cy + dy - r//2, cx + dx + r//2, cy + dy + r//2], fill=color)
    draw.rectangle([cx - 6, cy, cx + 6, cy + int(r*1.2)], fill=color)

def ensure_logos():
    ensure_dirs()
    # базовый шрифт (системный не гарантирован) — рисуем без текста на эмблеме,
    # подпись будет в caption сообщения
    for idx, (name, motto, bg, fg, emblem) in enumerate(TEAMS):
        out_path = os.path.join(LOGOS_DIR, f"team_{idx+1}.png")
        if os.path.isfile(out_path):
            continue
        img = Image.new("RGBA", (800, 800), bg + (255,))
        draw = ImageDraw.Draw(img)

        # «ореол» под эмблему
        halo = Image.new("RGBA", (800, 800), (255, 255, 255, 0))
        hdraw = ImageDraw.Draw(halo)
        hdraw.ellipse([200, 160, 600, 560], fill=(255, 255, 255, 40))
        halo = halo.filter(ImageFilter.GaussianBlur(12))
        img.alpha_composite(halo)

        # эмблема
        cx, cy, r = 400, 380, 180
        if emblem == "leaf":   draw_leaf(draw, cx, cy, r, fg)
        elif emblem == "tusk": draw_tusk(draw, cx, cy, r, fg)
        elif emblem == "hammer": draw_hammer(draw, cx, cy, r, fg)
        elif emblem == "dragon": draw_dragon(draw, cx, cy, r, fg)
        elif emblem == "clover": draw_clover(draw, cx, cy, r, fg)

        # легкая виньетка
        v = Image.new("L", (800, 800), 0)
        vdraw = ImageDraw.Draw(v)
        vdraw.ellipse([80, 80, 720, 720], fill=255)
        v = v.filter(ImageFilter.GaussianBlur(90))
        vignette = Image.new("RGBA", (800, 800), (0, 0, 0, 200))
        vignette.putalpha(v.point(lambda p: 255 - p))
        img = Image.alpha_composite(img, vignette)

        img.convert("RGB").save(out_path, "PNG", optimize=True)

def get_logo_path(team_index: int) -> str:
    ensure_logos()
    return os.path.join(LOGOS_DIR, f"team_{team_index+1}.png")

# ---------- UI ----------
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

# ---------- Анимации ----------
async def send_d20_animation(message: types.Message):
    # Если есть видео/гиф кубика — отправляем; иначе имитируем текстом
    path = file_if_exists(os.path.join(ASSETS_DIR, "d20.mp4"),
                          os.path.join(ASSETS_DIR, "d20.gif"))
    if path:
        await message.answer_animation(FSInputFile(path), caption="Судьба решается...")
    else:
        # Текстовая имитация «падения» кубика (несколько редактирований)
        txts = ["Бросаю d20…", "Бросаю d20… ░", "Бросаю d20… ░░", "Бросаю d20… ░░▒", "Бросаю d20… ░░▒▓", "Бросаю d20… ░░▒▓█"]
        msg = await message.answer(txts[0])
        for t in txts[1:]:
            await asyncio.sleep(0.35)
            await msg.edit_text(t)


await asyncio.sleep(0.3)

async def reveal_with_fog(chat_id: int, bot: Bot, photo_path: str, caption: str, reply_markup=None):
    # Если есть «туман» — отправляем как анимацию перед карточкой, иначе мягкое текстовое появление
    fog = file_if_exists(os.path.join(ASSETS_DIR, "fog.mp4"),
                         os.path.join(ASSETS_DIR, "fog.gif"))
    if fog:
        await bot.send_animation(chat_id, FSInputFile(fog), caption="Туман рассеивается…")
        await asyncio.sleep(0.8)
        await bot.send_photo(chat_id, FSInputFile(photo_path), caption=caption, reply_markup=reply_markup)
    else:
        # Мягкое появление (ступенчатое сообщение)
        msg = await bot.send_message(chat_id, "Туман сгущается… 🌫️")
        await asyncio.sleep(0.6)
        await bot.edit_message_text("Туман рассеивается…", chat_id, msg.message_id)
        await asyncio.sleep(0.6)
        await bot.send_photo(chat_id, FSInputFile(photo_path), caption=caption, reply_markup=reply_markup)

# ---------- Бот ----------
bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

@dp.message(CommandStart())
async def on_start(message: types.Message):
    init_db()
    ensure_logos()
    await message.answer(
        "Привет! Жми «🎲 Определи мою судьбу», и я распределю тебя в одну из 5 команд ровно и справедливо.",
        reply_markup=main_kb()
    )

@dp.message(Command("stats"))
async def on_stats_cmd(message: types.Message):
    init_db()
    await message.answer(stats_text())

@dp.message(Command("myteam"))
async def on_myteam_cmd(message: types.Message):
    init_db()
    team = get_player_team(message.from_user.id)
    if team is None:
        await message.answer("Ты ещё не распределён. Жми кнопку ниже.", reply_markup=main_kb())
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
        await cb.message.edit_text("Ты ещё не распределён. Жми кнопку ниже.", reply_markup=main_kb())
    else:
        await cb.message.delete()
        await bot.send_photo(cb.message.chat.id, FSInputFile(get_logo_path(team)), caption=team_caption(team), reply_markup=main_kb())
    await cb.answer()

@dp.callback_query(F.data == "join")
async def on_join(cb: types.CallbackQuery):
    init_db()
    user_id = cb.from_user.id
    team_existing = get_player_team(user_id)
    await cb.answer()  # моментальный ответ на «нажатие»

    # 1) Анимация броска d20
    await send_d20_animation(cb.message)

    # Если уже распределён — просто показать
    if team_existing is not None:
        await reveal_with_fog(
            cb.message.chat.id, bot,
            photo_path=get_logo_path(team_existing),
            caption=team_caption(team_existing),
            reply_markup=main_kb()
        )
        return

    # 2) Балансируем и сохраняем
    team_idx = pick_balanced_team()
    insert_player(
        user_id=cb.from_user.id,
        username=cb.from_user.username or "",
        full_name=(cb.from_user.full_name or "").strip(),
        team_index=team_idx
    )

    # 3) «Туманное» появление карточки команды (название жирным, ниже девиз, и лого)
    await reveal_with_fog(
        cb.message.chat.id, bot,
        photo_path=get_logo_path(team_idx),
        caption=team_caption(team_idx),
        reply_markup=main_kb()
    )

# Точка входа
async def main():
    ensure_dirs()
    ensure_logos()
    print("Bot is running…")
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())