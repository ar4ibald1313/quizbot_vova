import logging
import os
import random
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# Логирование
logging.basicConfig(level=logging.INFO)

# Токен
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения")

bot = Bot(token=TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# База пользователей {user_id: "раса"}
user_db = {}

# Клавиатуры
def get_main_keyboard(user_id: int):
    if user_id in user_db:
        kb = [[KeyboardButton("Моя команда")], [KeyboardButton("Сбросить")]]
    else:
        kb = [[KeyboardButton("Определить мою судьбу")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Обработчики
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer("Привет! 👋", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message_handler(lambda msg: msg.text == "Определить мою судьбу")
async def define_destiny(message: types.Message):
    races = ["Эльфы", "Гномы", "Люди", "Орки"]
    choice = random.choice(races)
    user_db[message.from_user.id] = choice
    await message.answer(f"Ты теперь в команде: <b>{choice}</b>", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message_handler(lambda msg: msg.text == "Моя команда")
async def my_team(message: types.Message):
    team = user_db.get(message.from_user.id)
    if team:
        await message.answer(f"Ты в команде: <b>{team}</b>", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Определить мою судьбу"))
        await message.answer("Вы не определили свою судьбу", reply_markup=kb)

@dp.message_handler(lambda msg: msg.text == "Сбросить")
async def reset_team(message: types.Message):
    user_db.pop(message.from_user.id, None)
    await message.answer("База очищена", reply_markup=get_main_keyboard(message.from_user.id))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
