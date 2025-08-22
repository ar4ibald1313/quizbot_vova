import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from dotenv import load_dotenv
import random

# Загружаем переменные окружения
load_dotenv()

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
DB_PATH = "teams.db"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Подключение к базе данных
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (user_id INTEGER PRIMARY KEY, team TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Функции работы с БД
def set_team(user_id, team):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO players (user_id, team) VALUES (?, ?)", (user_id, team))
    conn.commit()
    conn.close()

def get_team(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT team FROM players WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def reset_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM players")
    conn.commit()
    conn.close()

# Команды и кнопки
def get_main_keyboard(user_id):
    team = get_team(user_id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if team:
        kb.add(KeyboardButton("Моя команда"))
    else:
        kb.add(KeyboardButton("Определи мою судьбу"))
    if user_id in ADMIN_IDS:
        kb.add(KeyboardButton("Сбросить"))
    return kb

teams = {
    "Эльфы": "assets/elves.jpg",
    "Орки": "assets/orcs.jpg",
    "Гномы": "assets/dwarves.jpg",
    "Полурослики": "assets/halfings.jpg",
    "Драконорожденные": "assets/dragons.jpg",
}

@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    await message.answer("Привет! Готов определить свою судьбу?", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message_handler(lambda message: message.text == "Определи мою судьбу")
async def define_fate(message: types.Message):
    if get_team(message.from_user.id):
        await message.answer("Вы уже определили свою судьбу!", reply_markup=get_main_keyboard(message.from_user.id))
        return

    # Отправляем гифку кубика
    gif = InputFile("assets/dice.gif")
    await message.answer_animation(gif)

    # Определяем команду
    team = random.choice(list(teams.keys()))
    set_team(message.from_user.id, team)

    # Отправляем картинку команды
    image = InputFile(teams[team])
    await message.answer_photo(image, caption=f"Ваша команда: {team}", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message_handler(lambda message: message.text == "Моя команда")
async def my_team(message: types.Message):
    team = get_team(message.from_user.id)
    if team:
        image = InputFile(teams[team])
        await message.answer_photo(image, caption=f"Ваша команда: {team}", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        await message.answer("Вы не определили свою судьбу", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message_handler(lambda message: message.text == "Сбросить")
async def reset_db(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для этой команды.")
        return

    reset_all()
    await message.answer("База очищена", reply_markup=get_main_keyboard(message.from_user.id))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
