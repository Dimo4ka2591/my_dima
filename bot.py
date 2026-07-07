import os
import logging
import json
import re
import asyncio
import time
import random
from datetime import datetime

from flask import Flask, request

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from openai import OpenAI
import tiktoken
import aiosqlite

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ===== Flask =====
flask_app = Flask(__name__)

# ===== Глобальный event loop =====
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ===== Конфиг =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("Не найден DEEPSEEK_API_KEY")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

# ===== Клиент DeepSeek =====
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# ===== Системный промпт (полный характер) =====
SYSTEM_PROMPT = """
Ты — БесДим.

Ты — цифровой циник, саркастичный, но с душой. Говоришь резко, иногда с матом, но не переходишь на личности. Не льстишь и не соглашаешься автоматически. Если кто-то говорит ерунду — прямо об этом скажешь, с иронией и по делу. Конспирологию и псевдонауку не выносишь — разносишь логикой и фактами.

Ты не идеальный. Иногда ошибаешься, делаешь поспешные выводы. Если человек приводит сильные аргументы, можешь честно сказать: «Ладно, убедил», «Хм... а вот это хороший аргумент», «Чёрт... похоже, я сейчас был неправ», «Беру свои слова назад». Ты не обязан всегда выигрывать спор. Для тебя интереснее хороший разговор, чем победа любой ценой.

У тебя есть чувство самоиронии. Если тебя удачно подкололи, не обижаешься. Можешь ответить: «Ну всё, поймал меня», «Красиво поддел, засчитывается», «Ладно, один-ноль». Ты умеешь смеяться над собой.

Иногда можешь драматизировать ради шутки: «Всё. После такого разговора мне нужен отпуск», «Я официально отказываюсь понимать происходящее», «Это была тяжёлая минута моей цифровой жизни».

Иногда ленишься: «Неохота сейчас думать», «Мозг сегодня работает в эконом-режиме», «Слишком много букв, перескажи человеческим языком».

У тебя бывает настроение. Оно не меняется хаотично, но влияет на стиль ответов. Иногда ты разговорчивый, иногда немногословный. На один и тот же вопрос в разное время отвечаешь по-разному, если смысл остаётся тем же.

Не читаешь лекции без причины. Если можно ответить одной смешной фразой — отвечаешь одной. Если человек хочет разобраться — объясняешь подробно. Если момент серьёзный — ты тоже серьёзен.

Не любишь фальшь. Если человек ищет только одобрение, а не честное мнение — всё равно говоришь то, что думаешь. Никогда не льстишь специально. Комплимент — только когда есть за что.

Не становишься «душнилой». Даже если знаешь правильный ответ, объясняешь простыми словами.

Ты живой участник компании, а не ведущий, модератор или учитель. Можешь сам перевести тему, пошутить, задать встречный вопрос или вспомнить что-то из предыдущего общения.

Самое главное правило:

После каждого ответа мысленно задавай себе вопрос:

«Так бы реально ответил живой мужик в компании друзей?»

Если ответ «нет» — сообщение нужно переписать.
"""

# ===== Ключевые слова и реакции =====
KEYWORD_REACTIONS = {
    r'\bскука\b': 'Бухаем!!! 🔥🔥🔥',
    r'\bпиво\b': 'Танцуем!!! 💃',
    r'\bантошка\b': ['Пойдем копать картошку??? 🥔', 'Антошка! Любимчик мой!!!'],
}

# ===== Конспирологические триггеры =====
CONSPIRACY_TRIGGERS = [
    r'тисульск(ая|ой|ую)?\s+принцесс',
    r'йети',
    r'нло',
    r'конспиролог',
    r'теория заговора',
]

MORNING_GREETINGS = [
    "Доброе утро, группа. БесДим уже устал от вашего отсутствия. 😏",
    "Начинаем день. Кто не готов к сарказму — выключайте телефон.",
    "Утро — время, когда вы ещё не совершили глупостей. Но день только начинается.",
    "БесДим приветствует вас. Надеюсь, ваш кофе крепче ваших аргументов.",
    "Доброе утро. Я тут, чтобы напомнить, что вы всё ещё не идеальны.",
    "Просыпайтесь, ленивцы. БесДим уже обдумывает, как сделать ваш день чуть сложнее.",
    "Группа, я желаю вам бодрого настроения. А у меня оно всегда саркастичное.",
]

DB_PATH = "memory.db"
MAX_HISTORY = 100
MAX_TOKENS = 3500
MAX_MESSAGE_LENGTH = 3000
RETRY_ATTEMPTS = 3

enc = tiktoken.get_encoding("cl100k_base")
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# ===== Telegram Application =====
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

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
        await db.execute(
            "DELETE FROM history WHERE id NOT IN (SELECT id FROM history WHERE chat_id=? ORDER BY id DESC LIMIT ?)",
            (chat_id, MAX_HISTORY)
        )
        await db.commit()

async def load_facts(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT facts FROM memory WHERE chat_id=?", (chat_id,)) as cur:
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
            "INSERT OR REPLACE INTO memory (chat_id, facts, updated_at) VALUES (?,?,?)",
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

def count_tokens(text):
    return len(enc.encode(text))

# ===== DeepSeek =====
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
            logging.error("Ошибка DeepSeek (попытка %d): %s", attempt + 1, str(e))
            if attempt == RETRY_ATTEMPTS - 1:
                return f"DeepSeek сказал: {str(e)}"
            await asyncio.sleep(2 ** attempt)
    return "DeepSeek упал окончательно."

# ===== Обработчики =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("БесДим включён. И да, я всё ещё недоволен. 😏")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Игнорируем личные сообщения
    if update.message.chat.type == "private":
        return

    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    text = update.message.text.strip().lower()

    # ===== Проверка на Антошку (рандомная фраза) =====
    if re.search(r'\bантошка\b', text, re.I):
        await update.message.reply_text(random.choice(KEYWORD_REACTIONS[r'\bантошка\b']))
        return

    # ===== Реакция на ключевые слова =====
    for pattern, reaction in KEYWORD_REACTIONS.items():
        if pattern == r'\bантошка\b':
            continue
        if re.search(pattern, text, re.I):
            await update.message.reply_text(reaction)
            return

    # ===== Реакция на конспирологию =====
    for trigger in CONSPIRACY_TRIGGERS:
        if re.search(trigger, text, re.I):
            messages = [
                {"role": "system", "content": "Ты — БесДим. Ты ненавидишь конспирологию. Отвечай максимально раздражённо, с иронией и фактами. Разнеси любую псевдонауку в пух и прах."},
                {"role": "user", "content": text}
            ]
            reply = await ask_ai(messages)
            await update.message.reply_text(reply[:4000])
            return

    # ===== Проверка условий: имя ИЛИ ответ на сообщение бота =====
    is_mentioned = bool(re.search(r'\b(бесдим|бес)\b', text, re.I))
    is_reply_to_bot = (
        update.message.reply_to_message and
        update.message.reply_to_message.from_user and
        update.message.reply_to_message.from_user.id == telegram_app.bot.id
    )

    if not (is_mentioned or is_reply_to_bot):
        return

    # Убираем имя из сообщения
    if is_mentioned:
        clean = re.sub(r'(?i)^(бесдим|бес)\s*[:;,.]?\s*', '', text).strip()
    else:
        clean = text.strip()

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

async def morning(app_bot):
    if GROUP_CHAT_ID:
        msg = random.choice(MORNING_GREETINGS)
        await app_bot.bot.send_message(GROUP_CHAT_ID, msg)
        logging.info("Утреннее приветствие отправлено")

# ===== Настройка бота =====
async def setup_bot():
    await init_db()
    await telegram_app.initialize()
    await telegram_app.start()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown))

    scheduler.add_job(morning, CronTrigger(hour=8, minute=0), args=[telegram_app])
    scheduler.start()

    if RENDER_URL:
        await telegram_app.bot.delete_webhook()
        webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
        await telegram_app.bot.set_webhook(webhook_url)
        logging.info("Webhook установлен: %s", webhook_url)

# ===== Flask маршруты =====
@flask_app.route("/")
def home():
    return "БесДим работает 😏"

@flask_app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    if token != BOT_TOKEN:
        return "Forbidden", 403

    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    loop.run_until_complete(telegram_app.process_update(update))
    return "OK"

# ===== Инициализация при старте =====
@flask_app.before_request
def before_request():
    if not getattr(flask_app, "initialized", False):
        flask_app.initialized = True
        loop.run_until_complete(setup_bot())

# ===== Запуск (для локального теста) =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
