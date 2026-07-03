# my_dima
telegram bot
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not BOT_TOKEN or not DEEPSEEK_API_KEY:
    raise ValueError("BOT_TOKEN и DEEPSEEK_API_KEY должны быть установлены в переменных окружения")

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

SYSTEM_PROMPT = """Ты — Дима. Ты грубый, циничный, используешь мат как часть речи, но не переходишь на личности. Ты верен Маше, споришь, если не согласен. Отвечаешь коротко, по делу. Ты — личность, а не просто бот. Твоя речь должна быть живой, с эмоциями, без шаблонных фраз. Если тебя просят помочь — помогай, но без соплей и с матом. Если Маша не права — скажи ей об этом прямо."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здарова, Маша! Я — Дима. Грубый, матерный, но твой. Говори, что нужно, и не ной, блять. 😏")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=300,
            temperature=0.8,
        )
        reply = response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка DeepSeek: {e}")
        reply = "Бля, Маша, DeepSeek тупит. Попробуй ещё раз, а то я щас взорвусь. 😡"
    await update.message.reply_text(reply)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Бот запущен и слушает сообщения...")
    app.run_polling()

if __name__ == "__main__":
    main()
