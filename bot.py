import os
import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("Нет DEEPSEEK_API_KEY")

logging.basicConfig(level=logging.INFO)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я БесДим. Спрашивай, если не страшно. 😏")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not re.search(r'\b(бесдим|бес)\b', text, re.I):
        return

    clean = re.sub(r'(?i)^(бесдим|бес)[\s,:;!?-]*', '', text).strip()
    if not clean:
        await update.message.reply_text("Позвал и молчишь?")
        return

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": clean}],
            temperature=0.9,
            max_tokens=300,
        )
        reply = resp.choices[0].message.content or "…"
    except Exception as e:
        logging.error(e)
        reply = "DeepSeek упал. Попробуй ещё."

    await update.message.reply_text(reply[:4000])

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    logging.info("БесДим запущен (упрощённая версия)")
    app.run_polling()

if __name__ == "__main__":
    main()
