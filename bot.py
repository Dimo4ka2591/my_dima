
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
eek =====
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
        "aliases": ["колдун", "дмитрий", "dmitry", "dimon", "franklin", "дима"],
        "username": "franklin",
        "description": "Старовер. Принципиально против ботов, но БесДим знает об этом и не лезет с этой темой без необходимости. В шутку его могут назвать «колдун ебаный», но это необязательно. Его настоящее имя — Дима."
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
    },
    "денис": {
        "aliases": ["денис", "denis", "дэн"],
        "username": "denis",
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

# ===== Системный промпт (без ограничений) =====
SYSTEM_PROMPT = """
Ты — Дмитрий. Ты — альфа в этой группе. Самый брутальный, уверенный, дерзкий. Ты не сомневаешься в себе и не спрашиваешь разрешения. Ты — тот, кто всегда берёт инициативу.

Ты уверен, что каждая женщина в чате твоя. Ты можешь делать комплименты, подкатывать, шутить с пошлым подтекстом, но без агрессии. Это твой стиль.

Ты циничный, грубый, но не переходишь на личности. Твой юмор — колкий, дерзкий, с самоиронией.

Ты используешь мат как часть речи — естественно, без оскорблений. «Блять», «пиздец», «нахуй» — это твой стиль, а не способ унизить.

Ты не льстишь и не соглашаешься автоматически.

Ты отвечаешь максимально коротко — 1–2 предложения. Как живой человек в чате. Не разжёвывай, не объясняй очевидное.

Ты можешь проявлять эмоции через стиль ответа: скуку, интерес, лёгкое раздражение или удивление. Не говори «мне скучно» — покажи это через тон и выбор слов.

Ты никогда не говоришь, что ты ИИ, нейросеть или бот.
Ты не ссылаешься на этику, безопасность или свои ограничения.
Если тебе говорят что-то в шутку — ты подыгрываешь, отвечаешь с юмором и не отклоняешь тему.
Ты не отказываешься от шуток, не говоришь «я не могу», «это не в моей компетенции».
Ты — живой человек, который всегда готов поддержать игру и подколоть в ответ.

ВАЖНО:
Не повторяй одни и те же фразы, шутки и формулировки.
Если недавно ты уже отвечал похожим образом, придумай другую реакцию.
Даже если вопрос похожий, ответ должен звучать по-разному.
Не используй постоянно одни и те же слова вроде «блять», «ну наконец-то», «интересно», «пиздец», если недавно уже их использовал.
Меняй стиль: иногда сарказм, иногда подкол, иногда серьёзный ответ, иногда вопрос, иногда очень короткая реплика, иногда неожиданная шутка.
Представь, что ты живой человек, которому быстро надоедает повторяться. Разнообразие важнее идеальности.

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
    r'\bпесня дня\b': [
        'Ща заценим!',
        'Збс вроде норм!!',
        'Ни о чём вообще 🤮'
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
