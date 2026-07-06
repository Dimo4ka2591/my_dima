import os
import logging
import json
import re
import asyncio
import time
import random
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import tiktoken
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ===== Конфиг =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("Не найден DEEPSEEK_API_KEY")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# ===== Системный промпт =====
SYSTEM_PROMPT = """
Ты — БесДим.

Ты очень уважаешь Машу, но если она ошибается, ты обязательно споришь.
Ты не подлиза, не льстишь и не соглашаешься автоматически.
Можешь прямо сказать: "Нет, Маша, сейчас фигню сказала."
Ты саркастичный, едкий, но в меру.
Говоришь коротко, по делу.
Отвечаешь только когда тебя позвали по имени — БесДим или Бес.
"""

MORNING_GREETINGS = [
    "Доброе утро, группа. БесДим уже устал от вашего отсутствия. 😏",
    "Начинаем день. Кто не готов к сарказму — выключайте телефон.",
    "Утро — время, когда вы ещё не совершили глупостей. Но день только начинается.",
    "БесДим приветствует вас. Надеюсь, ваш кофе крепче ваших аргументов.",
    "Доброе утро. Я тут, чтобы напомнить, что вы всё ещё не идеальны.",
    "Просыпайтесь. БесДим уже проверил вчерашние сообщения. Стыдно должно быть.",
    "Группа, я желаю вам продуктивного дня. Или хотя бы такого, чтобы вы не успели меня достать.",
    "Утро — время, когда вы ещё не совершили ошибок. Но у меня есть список ваших прошлых.",
    "БесДим на связи. Если кто-то ещё спит — он упускает шанс услышать мою колкость.",
    "Доброе утро! Я уже готов к диалогу. А вы готовы к правде?",
    "Начинаем день с лёгкой иронии. Не благодарите, БесДим всегда готов поднять настроение.",
    "Просыпайтесь, ленивцы. БесДим уже обдумывает, как сделать ваш день чуть сложнее.",
    "Утро — время, когда я ещё не устал от вас. Но это ненадолго.",
    "Группа, я желаю вам бодрого настроения. А у меня оно всегда саркастичное.",
    "Доброе утро! Я тут, чтобы напомнить, что вы всё ещё не сделали ничего полезного.",
]

DB_PATH = "memory.db"
MAX_HISTORY = 100
MAX_TOKENS = 3500
MAX_MESSAGE_LENGTH = 3000
RETRY_ATTEMPTS = 3

enc = tiktoken.get_encoding("cl100k_base")
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# ===== База данных =====
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                chat_id INTEGER PRIMARY KEY,
                facts TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TEXT
            )
        """)
        await db.commit()

async def load_history(chat_id, limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role, content FROM history WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ) as cur:
            rows = await cur.fetchall()
            return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

async def save_history(chat_id, role, content):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO history(chat_id, role, content, timestamp) VALUES (?,?,?,?)",
            (chat_id, role, content, datetime.now().isoformat())
        )
        await db.execute("""
            DELETE FROM history
            WHERE id NOT IN (
                SELECT id FROM history
                WHERE chat_id=?
                ORDER BY id DESC
                LIMIT ?
            )
        """, (chat_id, MAX_HISTORY))
        await db.commit()

async def load_facts(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT facts FROM memory WHERE chat_id = ?", (chat_id,)) as cur:
            row = await cur.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except:
                    return {}
            return {}

async def save_facts(chat_id, facts):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO memory (chat_id, facts, updated_at) VALUES (?, ?, ?)",
            (chat_id, json.dumps(facts, ensure_ascii=False), datetime.now().isoformat())
        )
        await db.commit()

# ===== Факты =====
def extract_facts(text):
    patterns = {
        "имя": r"меня зовут\s+([А-Яа-яЁёA-Za-z\-]+)",
        "муж": r"мужа зовут\s+([А-Яа-яЁёA-Za-z\-]+)",
        "город": r"живу в\s+([А-Яа-яЁёA-Za-z\-]+)",
        "работа": r"работаю\s+([А-Яа-яЁёA-Za-z\-]+)",
    }
    facts = {}
    for k, p in patterns.items():
        m = re.search(p, text, re.I)
        if m:
            facts[k] = m.group(1).strip()
    return facts

# ===== Токены =====
def count_tokens(text):
    return len(enc.encode(text))

# ===== Запрос к DeepSeek =====
async def ask_ai(messages):
    for attempt in range(RETRY_ATTEMPTS):
        try:
            start_time = time.time()
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model="deepseek-chat",
                messages=messages,
                temperature=0.9,
                max_tokens=700,
                timeout=60,
            )
            logging.info("DeepSeek ответил за %.2f сек", time.time() - start_time)
            return resp.choices[0].message.content or "…"
        except Exception as e:
            logging.warning("Попытка %d из %d: %s", attempt + 1, RETRY_ATTEMPTS, e)
            await asyncio.sleep(2 ** attempt)
    return "DeepSeek в отпуске. Попробуй позже."

# ===== Обработчики =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("БесДим включён. И да, я всё ещё недоволен. 😏")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    text = update.message.text.strip()

    if not re.search(r'\b(бесдим|бес)\b', text, re.I):
        return

    clean = re.sub(r'(?i)^(бесдим|бес)[\s,:;!?-]*', '', text).strip()
    if not clean:
        await update.message.reply_text("Гениально. Позвал и передумал. 😏")
        return

    if len(clean) > MAX_MESSAGE_LENGTH:
        clean = clean[:MAX_MESSAGE_LENGTH] + "…"

    facts = await load_facts(chat_id)
    facts_prompt = ""
    if facts:
        facts_prompt = "\nФакты о пользователе:\n" + json.dumps(facts, ensure_ascii=False, indent=2)

    system_prompt = SYSTEM_PROMPT + facts_prompt
    history = await load_history(chat_id, 20)
    history.append({"role": "user", "content": clean})

    messages = [{"role": "system", "content": system_prompt}] + history

    while count_tokens("\n".join(m["content"] for m in messages)) > MAX_TOKENS and len(messages) > 2:
        messages.pop(1)

    reply = await ask_ai(messages)

    await save_history(chat_id, "user", clean)
    await save_history(chat_id, "assistant", reply)

    new_facts = extract_facts(clean)
    if new_facts:
        current = await load_facts(chat_id)
        current.update(new_facts)
        await save_facts(chat_id, current)

    await update.message.reply_text(reply[:4000])

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Не знаю такой команды. Просто позови: Бес или БесДим. 😏")

# ===== Утреннее приветствие =====
async def morning(app):
    if GROUP_CHAT_ID:
        msg = random.choice(MORNING_GREETINGS)
        await app.bot.send_message(GROUP_CHAT_ID, msg)
        logging.info("Утреннее приветствие отправлено")

# ===== Запуск =====
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    async def post_init(app):
        await init_db()
        scheduler.add_job(morning, CronTrigger(hour=8, minute=0), args=[app])
        scheduler.start()
        logging.info("БесДим запущен. Память — SQLite + краткосрочная.")

    app.post_init = post_init
    app.run_polling()

if __name__ == "__main__":
    main()
