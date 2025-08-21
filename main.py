import logging
import random
import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен и админ ID
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Команды
teams = {
    "elves": {"name": "Эльфы", "motto": "Вечность за нами, победа в нас!", "image": "assets/elves.jpg"},
    "orcs": {"name": "Орки", "motto": "Кто сильнее — тот правее!", "image": "assets/orcs.jpg"},
    "dwarves": {"name": "Гномы", "motto": "Камень — крепость, сталь — наша песня!", "image": "assets/dwarves.jpg"},
    "halflings": {"name": "Полурослики", "motto": "Мал да удал, но удача велика!", "image": "assets/halfings.jpg"},
    "dragons": {"name": "Драконорожденные", "motto": "Огонь в крови — слава в делах!", "image": "assets/dragons.jpg"},
}

# Игроки
players = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Определи мою судьбу 🎲", callback_data="choose_team")]
    ]
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Сбросить команды", callback_data="reset")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Нажми кнопку, чтобы узнать свою команду:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "choose_team":
        user_id = query.from_user.id
        if user_id in players:
            await query.edit_message_text("Ты уже распределён!")
            return

        # Показать гифку кубика
        with open("assets/dice.gif", "rb") as gif:
            await query.message.reply_animation(gif)

        # Поиск минимально заполненной команды
        counts = {team: list(players.values()).count(team) for team in teams}
        min_count = min(counts.values())
        available = [t for t, c in counts.items() if c == min_count]
        chosen_team = random.choice(available)

        players[user_id] = chosen_team
        team = teams[chosen_team]

        # Показать результат
        with open(team["image"], "rb") as img:
            await query.message.reply_photo(
                photo=img,
                caption=f"✨ {team['name']} ✨\n{team['motto']}"
            )

    elif query.data == "reset":
        if query.from_user.id == ADMIN_ID:
            players.clear()
            await query.edit_message_text("✅ Все команды сброшены!")
        else:
            await query.edit_message_text("⛔ У тебя нет прав для этого.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling()

if __name__ == "__main__":
    main()
