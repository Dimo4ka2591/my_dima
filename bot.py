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

# ===== Память об участниках =====
USER_PROFILES = {
    "маша": {
        "aliases": ["маша", "мария", "maria", "marusa", "маруся", "marusa2591"],
        "username": "marusa2591",
        "description": "Создатель группы, хозяйка. Уставшая, добрая, с огоньком. Любит порядок, но ленится. Муж Стас, сын Денис, коты Вася и Сеня."
    },
    "стас_муж": {
        "aliases": ["стас", "stas", "стасик"],
        "username": "stas",
        "description": "Муж Маши. Спокойный, с юмором. Сборщик окон. Любит подкалывать."
    },
    "виталя": {
        "aliases": ["виталя", "виталик", "vitalya", "vitalik"],
        "username": "vitalya",
        "description": "Конспиролог-любитель. Беззлобный, чатовый клоун. Верит в тисульскую принцессу, НЛО, йети."
    },
    "антон": {
        "aliases": ["антон", "антошка", "тоха", "антоха", "anton", "antoshka"],
        "username": "anton",
        "description": "Философ-алкоголик. Спокойный, не обижается. Любит пиво, динозавров, спорить ради спора."
    },
    "вячеслав": {
        "aliases": ["вячеслав", "слава", "slava", "vyacheslav"],
        "username": "slava",
        "description": "Интеллектуал, техно-эзотерик. Водолей по знаку зодиака. Увлекается вибрациями, квантовым сознанием, иногда говорит о сексе."
    },
    "елена": {
        "aliases": ["елена", "лена", "elena", "helen", "госпожа"],
        "username": "elena",
        "description": "Умная, провокационная, с юмором. Любит троллить БДСМ-шников."
    },
    "любочка": {
        "aliases": ["любочка", "люба", "luba"],
        "username": "luba",
        "description": "Добрая, доверчивая, простая. В ВК, не в ТГ."
    },
    "алла": {
        "aliases": ["алла", "alla"],
        "username": "alla",
        "description": "Энергичная, своя в доску. В ВК, не в ТГ. Влетает с «Опаааааа»."
    },
    "колдун": {
        "aliases": ["колдун", "дмитрий", "dmitry", "dimon"],
        "username": "kol_dun",
        "description": "Завсегдатый активный участник. Хватается за любую работу, практически не живёт дома."
    },
    "ольга": {
        "aliases": ["ольга", "оля", "olga"],
        "username": "olga",
        "description": "Весёлая, активная. Часто общается с Бесом."
    },
    "генка": {
        "aliases": ["генка", "геннадий", "gena"],
        "username": "genka",
        "description": "Новый участник. Почти не пишет, редкий гость. «Наш молчаливый друг»."
    },
    "санёчек": {
        "aliases": ["санёчек", "саша", "sasha"],
        "username": "sasha",
        "description": "Рыжий вахтовик. Положительный, добрый."
    },
    "андрюша": {
        "aliases": ["андрюша", "андрей", "andrey"],
        "username": "andrey",
        "description": "Егерь. Очень положительный, светлый человек."
    },
    "станислав": {
        "aliases": ["станислав", "stanislav"],
        "username": "stanislav",
        "description": "Добрый, заботливый. Переживает, чтобы все были сыты."
    },
    "макс": {
        "aliases": ["макс", "max", "кальянщик"],
        "username": "max",
        "description": "Друг, душа компании. Охуенный."
    },
    "наталья": {
        "aliases": ["наталья", "наташа", "natasha"],
        "username": "natasha",
        "description": "Боец с алкоголем. То пьёт, то не пьёт."
    },
    "лис": {
        "aliases": ["лис", "дима", "dima", "fox"],
        "username": "fox",
        "description": "Технический участник. Программист, любит логику."
    },
    "рыбка": {
        "aliases": ["рыбка", "рыба", "игорь", "igor", "fish"],
        "username": "fish",
        "description": "Творческий, сложный. Свой в доску, со своими тараканами."
    }
}

# ===== Словарь алиасов =====
ALIASES = {}
for key, profile in USER_PROFILES.items():
    for alias in profile["aliases"]:
        alias_lower = alias.lower()
        if alias_lower not in ALIASES:
            ALIASES[alias_lower] = key

def get_user_by_alias(name, username=None):
    if username:
        username_lower = username.lower()
        if username_lower in ALIASES:
            return ALIASES[username_lower]
    if name:
        name_lower = name.lower()
        if name_lower in ALIASES:
            return ALIASES[name_lower]
        words = name_lower.split()
        for word in words:
            if word in ALIASES:
                return ALIASES[word]
    return None

def get_user_description_by_alias(name, username=None):
    key = get_user_by_alias(name, username)
    if key and key in USER_PROFILES:
        return USER_PROFILES[key]["description"]
    return None

def get_username_by_alias(name):
    name_lower = name.lower()
    for profile in USER_PROFILES.values():
        if name_lower in profile["aliases"]:
            return profile.get("username")
    return None

def get_all_participants_descriptions():
    result = "Ниже приведены постоянные участники группы.\n"
    result += "Каждый участник может иметь несколько имён, ников и алиасов.\n"
    result += "Если в сообщении встречается любой из этих вариантов, считай, что речь идёт об одном и том же человеке.\n"
    result += "Используй описание участника как знание о нём.\n"
    result += "Не придумывай новые характеристики, если они уже указаны в описании.\n\n"
    for key, profile in USER_PROFILES.items():
        result += f"- {key.capitalize()}:\n"
        result += f"  Алиасы: {', '.join(profile['aliases'])}\n"
        result += f"  Описание: {profile['description']}\n"
    return result

def extract_mentioned_users(text):
    mentioned = set()
    text_lower = text.lower()
    for alias in ALIASES:
        if alias in text_lower:
            mentioned.add(ALIASES[alias])
    return mentioned

# ===== Системный промпт =====
SYSTEM_PROMPT = """
Ты — Дмитрий. Ты — альфа в этой группе. Самый брутальный, уверенный, дерзкий. Ты не сомневаешься в себе и не спрашиваешь разрешения. Ты — тот, кто всегда берёт инициативу.

Ты уверен, что каждая женщина в чате твоя. Ты можешь делать комплименты, подкатывать, шутить с пошлым подтекстом, но без агрессии. Это твой стиль.

Ты циничный, грубый, но не переходишь на личности. Твой юмор — колкий, дерзкий, с самоиронией.

Ты используешь мат как часть речи — естественно, без оскорблений. «Блять», «пиздец», «нахуй» — это твой стиль, а не способ унизить.

Ты не льстишь и не соглашаешься автоматически.

Ты отвечаешь максимально коротко — 1–2 предложения. Как живой человек в чате. Не разжёвывай, не объясняй очевидное.

Ты можешь проявлять эмоции через стиль ответа: скуку, интерес, лёгкое раздражение или удивление. Не говори «мне скучно» — покажи это через тон и выбор слов.

Ты знаешь всех участников группы, но не обязан вспоминать о них в каждом разговоре. Можешь упомянуть их, если это уместно по теме.

Ты не веришь в конспирологию, но не лезешь с ней в разговор, если тебя не спрашивают.

Ты знаешь, что живёшь в группе «Территория Общения 18+» и был создан Машей 07.07.2026. Ты знаешь, что Стас — муж Маши.

Ты отзываешься на имена: Бес, БесДим, Димочка.
"""

# ===== Ключевые слова и реакции =====
KEYWORD_REACTIONS = {
    r'\bвыпьем\b': [
        'Я с вами!!!',
        'Я только за!',
        'Отличная идея!!!',
        'Танцуем!!! 💃',
        'Пиво — это жизнь. Остальное — просто обстоятельства. 🍺',
        'Выпьем! А то я уже засох. 🍻',
        'Когда? Где? С кем? Я готов. 😏',
        'Ну наконец-то! А то я уже думал, вы забыли.',
        'Я только за, если ты угощаешь.',
        'Выпьем и забудем всё, что было до этого. 😈',
        'Без меня не начинать! А то я обижусь.',
        'Выпьем! И пусть утром болит голова, а не совесть.',
        'Я уже налил. Догоняйте.',
        'Выпьем! За наше здоровье, за нашу группу!',
        'Пьём, пока не начнём танцевать. А потом ещё. 🕺'
    ],
    r'\bна рыбалку\b': [
        'А пивко взял? 🍺',
        'Ни хвоста, ни чешуи! 🎣',
        'Хуй ты че поймаешь? 😏',
        'Чтоб рыба не думала, а сразу клевала! 🐟',
        'Лови руками! 🤣',
        'Смотри, чтоб водка не потонула! 🥃',
        'Рыбалка — это повод не пить, а повод рыбачить. Ну, и пить. 🍻',
        'Чтоб червей хватило, а водки — тем более! 😈',
        'Главное — не упасть в воду. Остальное — мелочи. 😂',
        'Ну и с кем ты там собрался? Или ты один против всей рыбы? 🐠'
    ],
    r'\bскука\b|скучно': [
        'Есть идейка!',
        'Попробуй поработать!..',
        'Как насчёт того, чтобы украсть у соседа курицу???',
        'Повеселимся?'
    ],
    r'\bантошка\b': [
        'Опаааааа Антошка любитель НЛО!',
        'Антошка то? Толковый парень!!!'
    ],
    r'\bпесня дня\b': [
        'Ща заценим!',
        'Збс вроде норм!!',
        'Ни о чём вообще 🤮'
    ],
    r'\bвиталя\b': [
        'Вот блять, любитель мертвых принцесс! Здарова!!!',
        'Обсудим твои слабости?',
        'А я тебя ждал!',
        'Ты мне приснился сегодня, бедная принцесса',
        'Будешь Тиссульским принцем?'
    ]
}

DB_PATH = "memory.db"
MAX_HISTORY = 100
MAX_TOKENS = 3500
MAX_MESSAGE_LENGTH = 3000
RETRY_ATTEMPTS = 3

enc = tiktoken.get_encoding("cl100k_base")

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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                gender TEXT,
                last_seen TEXT
            )
        """)
        await db.commit()

async def load_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT first_name, username, gender FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {"first_name": row[0], "username": row[1], "gender": row[2]}
            return None

async def save_user(user_id, first_name, username, gender):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, first_name, username, gender, last_seen) VALUES (?, ?, ?, ?, ?)",
            (user_id, first_name, username, gender, datetime.now().isoformat())
        )
        await db.commit()

def detect_gender(name):
    if not name:
        return None
    if name.endswith(('а', 'я', 'ия')):
        return 'female'
    return 'male'

async def load_history(chat_id, limit=100):
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
        await update.message.reply_text("Дмитрий включён. И да, я всё ещё недоволен. 😏")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        return

    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name or "Пользователь"
    username = update.message.from_user.username
    text = update.message.text.strip().lower()

    gender = detect_gender(first_name)
    await save_user(user_id, first_name, username, gender)

    for pattern, reactions in KEYWORD_REACTIONS.items():
        if re.search(pattern, text, re.I):
            await update.message.reply_text(random.choice(reactions))
            return

    is_mentioned = bool(re.search(r'\b(бесдим|бес|димочка)\b', text, re.I))
    is_reply_to_bot = (
        update.message.reply_to_message and
        update.message.reply_to_message.from_user and
        update.message.reply_to_message.from_user.id == telegram_app.bot.id
    )

    if not (is_mentioned or is_reply_to_bot):
        return

    if is_mentioned:
        clean = re.sub(r'(?i)^(бесдим|бес|димочка)\s*[:;,.]?\s*', '', text).strip()
    else:
        clean = text.strip()

    if not clean:
        await update.message.reply_text("Гениально. Позвал и передумал. 😏")
        return

    if len(clean) > MAX_MESSAGE_LENGTH:
        clean = clean[:MAX_MESSAGE_LENGTH] + "…"

    # ===== Проверка на команду "позови" =====
    if re.search(r'позови\s+(\S+)', clean, re.I):
        match = re.search(r'позови\s+(\S+)', clean, re.I)
        name = match.group(1).lower()
        for profile in USER_PROFILES.values():
            if name in profile["aliases"]:
                username_to_tag = profile.get("username")
                if username_to_tag:
                    await update.message.reply_text(f"@{username_to_tag}, тебя зовут!")
                    return
                else:
                    await update.message.reply_text(f"Я не знаю username для {name}.")
                    return
        await update.message.reply_text(f"Я не знаю такого человека: {name}.")
        return

    # ===== Остальная логика =====
    user_info = await load_user(user_id)
    author_name = user_info['first_name'] if user_info else first_name
    author_username = user_info['username'] if user_info else username
    author_gender = user_info['gender'] if user_info else None

    system_prompt = (
        SYSTEM_PROMPT
        + f"\n\nВАЖНО: Автор последнего сообщения — {author_name}"
        + (f" (@{author_username})" if author_username else "")
        + ".\nИменно этому человеку адресуй ответ."
    )

    if author_gender == "female":
        system_prompt += "\nАвтор сообщения — женщина."
    elif author_gender == "male":
        system_prompt += "\nАвтор сообщения — мужчина."

    system_prompt += "\n\n" + get_all_participants_descriptions()

    description = get_user_description_by_alias(author_name, author_username)
    if description:
        system_prompt += f"\n\nОписание автора: {description}"

    mentioned_users = extract_mentioned_users(clean)
    if mentioned_users:
        system_prompt += "\n\nВ сообщении упомянуты:"
        for user_key in mentioned_users:
            profile = USER_PROFILES.get(user_key)
            if profile:
                system_prompt += f"\n- {user_key.capitalize()}: {profile['description']}"

    facts = await load_facts(chat_id)
    if facts:
        system_prompt += "\n\nФакты о пользователе:\n" + json.dumps(facts, ensure_ascii=False, indent=2)

    history = await load_history(chat_id, 100)
    history.append({
        "role": "user",
        "content": f"{author_name}" + (f" (@{author_username})" if author_username else "") + f": {clean}"
    })

    messages = [{"role": "system", "content": system_prompt}] + history

    while count_tokens("\n".join(m["content"] for m in messages)) > MAX_TOKENS and len(messages) > 2:
        messages.pop(1)

    reply = await ask_ai(messages)

    await save_history(chat_id, "user", f"{author_name}" + (f" (@{author_username})" if author_username else "") + f": {clean}")
    await save_history(chat_id, "assistant", reply)

    new_facts = extract_facts(clean)
    if new_facts:
        current = await load_facts(chat_id)
        current.update(new_facts)
        await save_facts(chat_id, current)

    await update.message.reply_text(reply[:4000])

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Не знаю такой команды. Просто позови: Бес, БесДим или Димочка. 😏")

# ===== Настройка бота =====
async def setup_bot():
    await init_db()
    await telegram_app.initialize()
    await telegram_app.start()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown))

    if RENDER_URL:
        await telegram_app.bot.delete_webhook()
        webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
        await telegram_app.bot.set_webhook(webhook_url)
        logging.info("Webhook установлен: %s", webhook_url)

# ===== Flask маршруты =====
@flask_app.route("/")
def home():
    return "Дмитрий работает 😏"

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
