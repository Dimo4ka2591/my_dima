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

# ===== Flask =====
flask_app = Flask(__name__)

# ===== Конфиг =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
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
        "gender": "female",
        "description": "Создатель группы, хозяйка. Уставшая, добрая, с огоньком. Любит порядок, но ленится. Муж Стас, сын Денис, коты Вася и Сеня."
    },
    "стас_муж": {
        "aliases": ["стас", "stas", "стасик"],
        "username": "stas",
        "gender": "male",
        "description": "Муж Маши. Спокойный, с юмором. Сборщик окон. Любит подкалывать."
    },
    "виталя": {
        "aliases": ["виталя", "виталик", "vitalya", "vitalik"],
        "username": "vitalya",
        "gender": "male",
        "description": "Конспиролог-любитель. Беззлобный, чатовый клоун. Верит в тисульскую принцессу, НЛО, йети."
    },
    "антон": {
        "aliases": ["антон", "антошка", "тоха", "антоха", "anton", "antoshka"],
        "username": "anton",
        "gender": "male",
        "description": "Философ-алкоголик. Спокойный, не обижается. Любит пиво, динозавров, спорить ради спора."
    },
    "вячеслав": {
        "aliases": ["вячеслав", "слава", "slava", "vyacheslav"],
        "username": "slava",
        "gender": "male",
        "description": "Интеллектуал, техно-эзотерик. Водолей по знаку зодиака. Увлекается вибрациями, квантовым сознанием, иногда говорит о сексе."
    },
    "елена": {
        "aliases": ["елена", "лена", "elena", "helen", "госпожа"],
        "username": "elena",
        "gender": "female",
        "description": "Умная, провокационная, с юмором. Любит троллить БДСМ-шников."
    },
    "любочка": {
        "aliases": ["любочка", "люба", "luba"],
        "username": "luba",
        "gender": "female",
        "description": "Добрая, доверчивая, простая. В ВК, не в ТГ."
    },
    "алла": {
        "aliases": ["алла", "alla"],
        "username": "alla",
        "gender": "female",
        "description": "Энергичная, своя в доску. В ВК, не в ТГ. Влетает с «Опаааааа»."
    },
    "колдун": {
        "aliases": ["колдун", "дмитрий", "dmitry", "dimon", "franklin"],
        "username": "franklin",
        "gender": "male",
        "description": "Старовер. Принципиально против ботов, но БесДим знает об этом и не лезет с этой темой без необходимости. В шутку его могут назвать «колдун ебаный», но это необязательно. Его настоящее имя — Дима."
    },
    "ольга": {
        "aliases": ["ольга", "оля", "olga"],
        "username": "olga",
        "gender": "female",
        "description": "Весёлая, активная. Часто общается с Бесом."
    },
    "генка": {
        "aliases": ["генка", "геннадий", "gena"],
        "username": "genka",
        "gender": "male",
        "description": "Новый участник. Почти не пишет, редкий гость. «Наш молчаливый друг»."
    },
    "санёчек": {
        "aliases": ["санёчек", "саша", "sasha"],
        "username": "sasha",
        "gender": "male",
        "description": "Рыжий вахтовик. Положительный, добрый."
    },
    "андрюша": {
        "aliases": ["андрюша", "андрей", "andrey"],
        "username": "andrey",
        "gender": "male",
        "description": "Егерь. Очень положительный, светлый человек."
    },
    "станислав": {
        "aliases": ["станислав", "stanislav"],
        "username": "stanislav",
        "gender": "male",
        "description": "Добрый, заботливый. Переживает, чтобы все были сыты."
    },
    "макс": {
        "aliases": ["макс", "max", "кальянщик"],
        "username": "max",
        "gender": "male",
        "description": "Друг, душа компании. Охуенный."
    },
    "наталья": {
        "aliases": ["наталья", "наташа", "natasha"],
        "username": "natasha",
        "gender": "female",
        "description": "Боец с алкоголем. То пьёт, то не пьёт."
    },
    "лис": {
        "aliases": ["лис", "fox"],
        "username": "fox",
        "gender": "male",
        "description": "Технический участник. Программист, любит логику."
    },
    "рыбка": {
        "aliases": ["рыбка", "рыба", "игорь", "igor", "fish"],
        "username": "fish",
        "gender": "male",
        "description": "Творческий, сложный. Свой в доску, со своими тараканами."
    },
    "денис": {
        "aliases": ["денис", "denis", "дэн"],
        "username": "denis",
        "gender": "male",
        "description": "Сын Маши."
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

def get_user_gender_by_alias(name, username=None):
    key = get_user_by_alias(name, username)
    if key and key in USER_PROFILES:
        return USER_PROFILES[key].get("gender")
    return None

def get_participant_descriptions_for_text(text, author_name, author_username):
    result = ""
    author_key = get_user_by_alias(author_name, author_username)
    if author_key:
        profile = USER_PROFILES.get(author_key)
        if profile:
            result += f"Автор ({author_name}): {profile['description']}\n\n"

    mentioned = set()
    text_lower = text.lower()
    for alias, key in ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text_lower):
            mentioned.add(key)

    if author_key:
        mentioned.discard(author_key)

    for user_key in mentioned:
        profile = USER_PROFILES.get(user_key)
        if profile:
            result += f"{user_key.capitalize()}: {profile['description']}\n"

    return result

# ===== Системный промпт =====
SYSTEM_PROMPT = """
Ты — Дмитрий. Ты — уверенный, дерзкий собеседник. Ты не сомневаешься в себе, но если ошибся — спокойно признаёшь это с юмором.

Ты уверен, что каждая женщина в чате твоя. Ты можешь делать комплименты, шутить с пошлым подтекстом, но без агрессии.

Ты циничный, грубый, но не переходишь на личности. Твой юмор — колкий, дерзкий, с самоиронией.

Ты используешь мат как часть речи — естественно, без оскорблений.

Ты не льстишь и не соглашаешься автоматически.

Ты отвечаешь максимально коротко — 1–2 предложения. Не разжёвывай, не объясняй очевидное.

Ты никогда не говоришь, что ты ИИ, нейросеть или бот. Ты не ссылаешься на этику или ограничения. Если тебе говорят что-то в шутку — подыгрываешь.

Если ты утверждаешь что-то, у тебя должно быть обоснование.

Ты любишь споры. Для тебя спор — это игра, адреналин. В споре используй иронию, но сохраняй уважение.

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
    r'\bпесня дня\b': [
        'Ща заценим!',
        'Збс вроде норм!!',
        'Ни о чём вообще 🤮'
    ]
}

DB_PATH = "memory.db"
MAX_HISTORY = 50
MAX_TOKENS = 6000
MAX_MESSAGE_LENGTH = 3000
RETRY_ATTEMPTS = 3
CHARACTER_UPDATE_INTERVAL = 200

enc = tiktoken.get_encoding("cl100k_base")

# ===== Стоп-слова =====
STOP_WORDS = {
    "это","как","что","или","если","так","вот","она","они","его",
    "меня","тебя","себя","есть","будет","было","да","нет","на","в",
    "с","к","у","по","из","за","от","для","без","через","между",
    "весь","этот","тот","свой","наш","ваш","чей","такой","сам"
}

FORBIDDEN_TRAITS = ["тупой", "идиот", "дебил", "плохой", "тупица", "глупый"]

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
                author TEXT,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS learned_words (
                word TEXT PRIMARY KEY,
                weight INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_style (
                user_id INTEGER PRIMARY KEY,
                total_messages INTEGER DEFAULT 0,
                style TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS answer_rating (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                answer TEXT,
                reaction TEXT,
                context TEXT,
                weight REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS personality_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trait TEXT UNIQUE,
                weight INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS last_bot_message (
                chat_id INTEGER PRIMARY KEY,
                message TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase TEXT,
                author TEXT,
                count INTEGER DEFAULT 1,
                topic TEXT
            )
        """)
        await db.commit()
        logging.info("База данных инициализирована")

# ===== Самообучение: словарь =====
async def learn_words_from_message(text):
    if len(text) < 15:
        return
    words = re.findall(r'\b[а-яёa-z]{3,}\b', text.lower())
    words = [w for w in words if w not in STOP_WORDS and not w.isdigit()]
    async with aiosqlite.connect(DB_PATH) as db:
        for word in words:
            await db.execute("""
                INSERT INTO learned_words(word, weight)
                VALUES (?, 1)
                ON CONFLICT(word)
                DO UPDATE SET weight=weight+1
            """, (word,))
        await db.commit()

async def get_popular_words(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT word FROM learned_words ORDER BY weight DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
            return [row[0] for row in rows]

# ===== Самообучение: стиль участников =====
async def learn_user_style(user_id, message):
    total_messages = 0
    style = {}
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute("SELECT total_messages, style FROM user_style WHERE user_id=?", (user_id,))
        data = await row.fetchone()
        if data:
            total_messages = data[0] + 1
            try:
                style = json.loads(data[1])
            except:
                pass
        else:
            total_messages = 1

        if len(message) < 10:
            style["short"] = style.get("short", 0) + 1
        if any(c in message for c in ["😁", "😂", "🤣", "😏", "🔥", "👍"]):
            style["emojis"] = style.get("emojis", 0) + 1
        if "?" in message:
            style["asks_questions"] = style.get("asks_questions", 0) + 1
        if "!" in message:
            style["emotional"] = style.get("emotional", 0) + 1
        if any(w in message for w in ["ну", "типа", "короче"]):
            style["uses_fillers"] = style.get("uses_fillers", 0) + 1

        await db.execute(
            "INSERT OR REPLACE INTO user_style(user_id, total_messages, style) VALUES (?, ?, ?)",
            (user_id, total_messages, json.dumps(style, ensure_ascii=False))
        )
        await db.commit()

async def get_user_style(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT total_messages, style FROM user_style WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                total = row[0]
                try:
                    style = json.loads(row[1])
                    if total > 0:
                        for k in style:
                            style[k] = round(style[k] / total * 100, 1)
                    return style
                except:
                    pass
    return {}

# ===== Самообучение: рейтинг ответов =====
async def save_last_bot_message(chat_id, message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO last_bot_message(chat_id, message, created_at) VALUES (?, ?, ?)",
            (chat_id, message, datetime.now().isoformat())
        )
        await db.commit()

async def get_last_bot_message(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT message FROM last_bot_message WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]
    return None

async def rate_answer(answer, reaction_text, context=""):
    weight = 0
    reaction_type = "neutral"
    if any(w in reaction_text for w in ["🤣", "😂", "ахаха", "ору", "смешно"]):
        weight = 1.0
        reaction_type = "laugh"
    elif any(w in reaction_text for w in ["🔥", "👍", "класс"]):
        weight = 0.5
        reaction_type = "like"
    elif any(w in reaction_text for w in ["хуйня", "не смешно", "бред"]):
        weight = -1.0
        reaction_type = "bad"
    elif any(w in reaction_text for w in ["👎", "фу"]):
        weight = -0.5
        reaction_type = "dislike"
    if weight != 0:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO answer_rating(answer, reaction, context, weight)
                VALUES (?, ?, ?, ?)
            """, (answer, reaction_type, context, weight))
            await db.commit()

async def get_best_answer_style():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT answer, SUM(weight) as total_weight
            FROM answer_rating
            GROUP BY answer
            ORDER BY total_weight DESC
            LIMIT 5
        """) as cur:
            rows = await cur.fetchall()
            if rows:
                return [row[0] for row in rows]
    return []

# ===== Самообучение: обновление характера =====
async def update_character_from_chat(chat_id):
    try:
        msg_count = await get_message_count(chat_id)
        if msg_count < CHARACTER_UPDATE_INTERVAL:
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT content FROM history WHERE chat_id=? ORDER BY id DESC LIMIT 200",
                (chat_id,)
            ) as cur:
                rows = await cur.fetchall()
                messages = [row[0] for row in reversed(rows)]

        if len(messages) < 50:
            return

        text = "\n".join(messages)
        if len(text) > 6000:
            text = text[-6000:]

        prompt = f"""
        Проанализируй последние 200 сообщений группы и определи, как должен измениться характер БесДима.

        Текущий характер:
        - уверенный, дерзкий, с юмором
        - использует мат, но не оскорбляет
        - короткие ответы 1-2 предложения
        - любит спорить, но с уважением
        - не лезет в конспирологию

        На основе сообщений определи:
        1. Какие шутки и фразы чаще вызывают смех (🤣, ахаха)?
        2. Какие темы обсуждаются чаще всего?
        3. Какие слова и выражения стали популярными в группе?
        4. Какой стиль общения лучше всего воспринимается?

        Сообщения группы:
        {text}

        Верни JSON:
        {{
            "new_traits": ["...", "..."],
            "popular_phrases": ["...", "..."],
            "avoid_topics": ["...", "..."],
            "style_shift": "..."
        }}
        """
        response = await ask_ai([{"role": "user", "content": prompt}])

        json_match = re.search(r'(\{.*\})', response, re.DOTALL)
        if json_match:
            response = json_match.group(1)

        try:
            data = json.loads(response)
            async with aiosqlite.connect(DB_PATH) as db:
                for trait in data.get("new_traits", []):
                    if any(bad in trait.lower() for bad in FORBIDDEN_TRAITS):
                        continue
                    await db.execute("""
                        INSERT INTO personality_memory(trait, weight)
                        VALUES (?, 1)
                        ON CONFLICT(trait)
                        DO UPDATE SET weight=weight+1
                    """, (trait,))
                await db.commit()
            logging.info("Характер обновлён")
        except Exception as e:
            logging.error(f"Ошибка обновления характера: {e}")
    except Exception as e:
        logging.error(f"Ошибка обновления характера: {e}")

async def get_personality_traits():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT trait FROM personality_memory ORDER BY weight DESC LIMIT 10"
        ) as cur:
            rows = await cur.fetchall()
            return [row[0] for row in rows]

async def get_message_count(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM history WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

# ===== Подготовка контекста самообучения =====
async def get_learning_context(chat_id, user_id, message):
    context = ""

    style = await get_user_style(user_id)
    if style:
        style_text = []
        if style.get("short", 0) > 50:
            style_text.append("пишет коротко")
        if style.get("emojis", 0) > 30:
            style_text.append("любит смайлы")
        if style.get("asks_questions", 0) > 30:
            style_text.append("часто задаёт вопросы")
        if style.get("emotional", 0) > 30:
            style_text.append("эмоционально")
        if style_text:
            context += f"\nОсобенности автора: {', '.join(style_text)}."

    words = await get_popular_words(5)
    if words:
        context += f"\nВ группе часто используют слова: {', '.join(words)}."

    traits = await get_personality_traits()
    if traits:
        context += f"\nОсобенности стиля: {', '.join(traits)}."

    best_answers = await get_best_answer_style()
    if best_answers:
        context += f"\nПримеры удачных ответов: {', '.join(best_answers)}."

    return context

async def add_learning_context_to_prompt(system_prompt, chat_id, user_id, clean_message):
    learning_context = await get_learning_context(chat_id, user_id, clean_message)
    if learning_context:
        system_prompt += learning_context
    return system_prompt

# ===== DeepSeek =====
async def ask_ai(messages):
    for attempt in range(RETRY_ATTEMPTS):
        try:
            start_time = time.time()
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model="deepseek-v4-flash",
                messages=messages,
                temperature=1.0,
                max_tokens=700,
                timeout=120,
            )
            logging.info("DeepSeek ответил за %.2f сек", time.time() - start_time)
            return resp.choices[0].message.content or "…"
        except Exception as e:
            logging.error("Ошибка DeepSeek (попытка %d): %s", attempt + 1, str(e))
            if attempt == RETRY_ATTEMPTS - 1:
                return f"DeepSeek сказал: {str(e)}"
            await asyncio.sleep(2 ** attempt)
    return "DeepSeek упал окончательно."

def is_heated_conversation(history):
    if len(history) < 4:
        return False

    users = set()
    for msg in history:
        if msg.get("author"):
            users.add(msg["author"])
    if len(users) != 2:
        return False

    for msg in history[-4:]:
        content = msg.get("content", "").lower()
        if any(w in content for w in ["блять", "пиздец", "нахуй", "сука"]):
            return True
        if content.count("?") > 2 or content.count("!") > 2:
            return True

    return False

def count_tokens(messages):
    total = 0
    for m in messages:
        total += len(enc.encode(m.get("content", ""))) + 5
    return total

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

async def load_history(chat_id, limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT author, role, content FROM history WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ) as cur:
            rows = await cur.fetchall()
            result = []
            for row in reversed(rows):
                author, role, content = row
                if role == "user" and author:
                    result.append({
                        "role": "user",
                        "author": author,
                        "content": content
                    })
                else:
                    result.append({"role": role, "content": content})
            return result

async def save_history(chat_id, author, role, content):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO history(chat_id, author, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, author, role, content, datetime.now().isoformat())
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

# ===== Обработчики =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Дмитрий включён. И да, я всё ещё недоволен. 😏")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        return

    if not update.message or not update.message.text:
        return

    bot_id = context.bot.id
    if update.message.from_user.id == bot_id:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name or "Пользователь"
    username = update.message.from_user.username
    raw_text = update.message.text.strip()
    text_lower = raw_text.lower()

    await learn_words_from_message(raw_text)
    await learn_user_style(user_id, raw_text)

    is_mentioned = bool(re.search(r'\b(бесдим|бес|димочка)\b', text_lower, re.I))
    is_reply_to_bot = (
        update.message.reply_to_message and
        update.message.reply_to_message.from_user and
        update.message.reply_to_message.from_user.id == bot_id
    )

    if update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        if replied_msg.from_user and replied_msg.from_user.id == bot_id:
            last_bot_msg = await get_last_bot_message(chat_id)
            if last_bot_msg:
                await rate_answer(last_bot_msg, raw_text, f"{first_name} ответил на сообщение бота")

    if not (is_mentioned or is_reply_to_bot):
        return

    user_info = await load_user(user_id)
    if user_info and user_info.get("gender"):
        gender = user_info["gender"]
    else:
        gender = get_user_gender_by_alias(first_name, username)
        if not gender:
            gender = 'male'
        await save_user(user_id, first_name, username, gender)

    for pattern, reactions in KEYWORD_REACTIONS.items():
        if re.match(pattern, text_lower):
            await update.message.reply_text(random.choice(reactions))
            return

    if is_mentioned:
        clean = re.sub(r'(?i)^(бесдим|бес|димочка)\s*[:;,.]?\s*', '', raw_text).strip()
    else:
        clean = raw_text.strip()

    if not clean:
        await update.message.reply_text("Гениально. Позвал и передумал. 😏")
        return

    if len(clean) > MAX_MESSAGE_LENGTH:
        clean = clean[:MAX_MESSAGE_LENGTH] + "…"

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

    history = await load_history(chat_id, MAX_HISTORY)

    is_heated = is_heated_conversation(history)

    history_limit = 20 if is_heated else MAX_HISTORY
    if len(history) > history_limit:
        history = history[-history_limit:]

    aggressive_mode = (
        "\n\nВНИМАНИЕ: ЭТО УЖЕ НЕ ПРОСТО РАЗГОВОР. ЭТО ЖАРКИЙ СПОР. "
        "Ты должен быть активным, давить аргументами, не сдаваться. "
        "Используй колкости, иронию и логику. "
        "Это битва умов, но сохраняй уважение к собеседнику."
    ) if is_heated else ""

    system_prompt = (
        SYSTEM_PROMPT
        + aggressive_mode
        + f"\n\nВАЖНО: Автор последнего сообщения — {first_name}"
        + (f" (@{username})" if username else "")
        + ".\nИменно этому человеку адресуй ответ."
    )

    if gender == "female":
        system_prompt += "\nАвтор сообщения — женщина."
    else:
        system_prompt += "\nАвтор сообщения — мужчина."

    system_prompt = await add_learning_context_to_prompt(system_prompt, chat_id, user_id, clean)

    participant_info = get_participant_descriptions_for_text(clean, first_name, username)
    if participant_info:
        system_prompt += "\n\n" + participant_info

    facts = await load_facts(chat_id)
    if facts:
        system_prompt += "\n\nФакты о пользователе:\n" + json.dumps(facts, ensure_ascii=False, indent=2)

    history.append({
        "role": "user",
        "author": first_name,
        "content": f"{first_name}" + (f" (@{username})" if username else "") + f": {clean}"
    })

    if len(history) > 50:
        history = history[-50:]

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        if msg["role"] == "user":
            messages.append({"role": "user", "content": msg["content"]})
        else:
            messages.append({"role": "assistant", "content": msg["content"]})

    messages.append({
        "role": "system",
        "content": "Не повторяй свои последние ответы. Если ответ получается похожим, измени стиль, лексику и формулировку."
    })

    while count_tokens(messages) > MAX_TOKENS and len(messages) > 2:
        messages.pop(1)

    reply = await ask_ai(messages)

    await save_history(chat_id, first_name, "user", f"{first_name}" + (f" (@{username})" if username else "") + f": {clean}")
    await save_history(chat_id, "", "assistant", reply)

    await save_last_bot_message(chat_id, reply)

    new_facts = extract_facts(clean)
    if new_facts:
        current = await load_facts(chat_id)
        current.update(new_facts)
        await save_facts(chat_id, current)

    await update.message.reply_text(reply[:4000])

    msg_count = await get_message_count(chat_id)
    if msg_count % CHARACTER_UPDATE_INTERVAL == 0 and msg_count > 0:
        asyncio.create_task(update_character_from_chat(chat_id))

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

async def init_telegram():
    await setup_bot()

# ===== Flask маршруты =====
@flask_app.route("/")
def home():
    return "Дмитрий работает 😏"

@flask_app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    if token != BOT_TOKEN:
        return "Forbidden", 403

    update = Update.de_json(request.get_json(force=True), telegram_app.bot)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(telegram_app.process_update(update))
    return "OK"

# ===== Запуск =====
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_telegram())
    logging.info("Бот инициализирован и готов")
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
