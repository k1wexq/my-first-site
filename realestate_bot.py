#!/usr/bin/env python3
import asyncio
from collections import Counter
from telethon import TelegramClient, events
import matplotlib.pyplot as plt
from io import BytesIO
import re
from datetime import datetime, timedelta, timezone
from telethon import Button
import time
import logging
import sqlite3
import json
import hashlib
import os

# ------------------- БАЗА ДАННЫХ -------------------
class Database:
    def __init__(self, db_name='bot_state.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id INTEGER,
                chat_id INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (message_id, chat_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_texts (
                user_key TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        ''')
        self.conn.commit()
    
    def add_processed_message(self, message_id, chat_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO processed_messages (message_id, chat_id) VALUES (?, ?)',
            (message_id, chat_id)
        )
        self.conn.commit()
    
    def is_message_processed(self, message_id, chat_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND chat_id = ?',
            (message_id, chat_id)
        )
        return cursor.fetchone() is not None
    
    def add_user_text(self, user_key):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO user_texts (user_key) VALUES (?)',
            (user_key,)
        )
        self.conn.commit()
    
    def is_user_text_exists(self, user_key):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM user_texts WHERE user_key = ?',
            (user_key,)
        )
        return cursor.fetchone() is not None
    
    def get_stat(self, key, default=0):
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM stats WHERE key = ?', (key,))
        result = cursor.fetchone()
        return result[0] if result else default
    
    def set_stat(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO stats (key, value) VALUES (?, ?)',
            (key, value)
        )
        self.conn.commit()
    
    def increment_stat(self, key):
        current = self.get_stat(key)
        self.set_stat(key, current + 1)

# ------------------- КОНФИГУРАЦИЯ -------------------
class Config:
    # 🔐 API данные
    API_ID = 19244636
    API_HASH = '8a9a412c60f16d05b60b057233c1d6c2'
    BOT_TOKEN = '8414225285:AAG2p81hoOoN2VgUslB5Y5pjabpLYiEemt0'  # Твой токен
    
    # ✅ Целевая группа
    TARGET_CHAT = 'https://t.me/+KqjEK6oRykkwZGUy'
    
    # 🔑 Админ ID
    ADMIN_ID = 8043262634
    
    # ⚙️ Настройки
    MESSAGE_AGE_LIMIT_HOURS = 6
    
    # 🟢 Сигналы клиента
    NEED_WORDS = [
        "ищу", "ищем", "снять", "сниму", "снимем", "хочу снять", "хотим снять",
        "арендую", "арендовать", "нужна квартира", "нужен дом", "нужно жилье",
        "нужно жильё", "в поисках", "подскажите", "посоветуйте", "ищем жилье",
        "требуется квартира", "нужна аренда", "ищу аренду", "хочу арендовать",
        "ищу квартиру", "ищем квартиру", "сниму квартиру", "сниму дом",
        "ищу жилье", "ищу недвижимость"
    ]
    
    # 🏠 Сигналы жилья
    REAL_ESTATE_WORDS = [
        "квартира", "квартиру", "квартиры", "жильё", "жильe", "апартаменты",
        "апарт", "студия", "студию", "комната", "комнату", "однокомнатная",
        "двухкомнатная", "трёхкомнатная", "четырехкомнатная", "1+1", "2+1",
        "3+1", "4+1", "однушка", "двушка", "трёшка", "четверка", "спальня",
        "спальни", "комнаты", "дом", "таунхаус", "пентхаус", "апартаменты",
        "лофт", "малосемейка", "гостинка", "хрущевka", "брежневka", "помещение"
    ]
    
    # ❌ Чёрный список
    BLACKLIST = [
        "сдам", "сдаю", "сдаётся", "сдается", "сдавать", "сдаём", "сдаем",
        "риелтор", "риэлтор", "агент", "агентство", "агенты", "риелторы",
        "посредник", "посредники", "арендодатель", "собственник", "продам",
        "продаю", "продаётся", "продается", "продажа", "хозяин", "комиссия",
        "без комиссии", "процент", "процентов", "услуги", "подберу", "подберем",
        "подбор жилья", "подбор недвижимости", "клиенты", "поиск клиентов",
        "ваша квартира", "ваше жильe", "найду жилье", "найду жильё", "найдем жильe",
        "база квартир", "база недвижимости", "база объектов", "аренда квартир под ключ",
        "под ключ", "звоните", "обращайтесь", "пишите", "директ", "телефон",
        "подписка", "канал", "реклама", "объявление", "платная услуга", "предлагаю услугу",
        "услуга риелтора", "работаю по городу", "помогу снять", "помогу с арендой",
        "сопровождение", "оформление документов", "беру %", "беру процент", "уборка",
        "ремонт", "клиниng", "5000", "5.000", "5000₽", "5.000₽", "мастер", "сантехник",
        "электрик", "мебель", "сборка", "работа", "вакансия", "зарплата", "оплата",
        "на руки", "по завершению", "после ремонта", "генеральная уборка", "бот",
        "проверяю", "тестирую", "бригада", "бригаду", "шоп"
    ]
    
    # 🚫 Дополнительный фильтр
    ADDITIONAL_FILTERS = [
        "медсестр", "инъекц", "укол", "врач", "доктор", "больни", "клиник", "медицин",
        "лечен", "процедур", "капельниц", "укол", "инъекц", "медик", "медбрат", "фельдшер",
        "скорая", "аптек", "лекарств", "препарат", "ремонт", "строительств", "мастер",
        "сантехник", "электрик", "плиточник", "штукатур", "маляр", "строит", "инструмент",
        "дрель", "перфоратор", "болгарк", "штроблен", "отделочник", "строитель", "ремонтник",
        "монтажник", "установк", "монтаж", "продам", "куплю", "обменяю", "меняю", "отдам",
        "приму", "домино", "георгий", "лило", "хоть", "показывает", "наличие", "ищу работу",
        "работа для", "вакансия", "требуются", "требуется"
    ]

# ------------------- НАСТРОЙКА ЛОГГИРОВАНИЯ -------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("telethon").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ------------------- ИНИЦИАЛИЗАЦИЯ -------------------
db = Database()

# Исправляем подключение клиента
client = TelegramClient(
    'premium_bot_session', 
    Config.API_ID, 
    Config.API_HASH,
    connection_retries=None,  # Убираем ограничения попыток
    auto_reconnect=True,      # Автопереподключение
    request_retries=10,       # Увеличиваем попытки
    flood_sleep_threshold=60  # Увеличиваем порог сна
)

# ------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------
TARGET_CHAT_ID = None
monitoring_status = "🟢 Мониторинг 24/7"
start_time = datetime.now()
group_stats = Counter()
user_stats = Counter()
chat_title_cache = {}

# ------------------- УТИЛИТЫ -------------------
def hash_text(text):
    return hashlib.md5(text.encode()).hexdigest()

def get_georgia_time():
    return datetime.now(timezone(timedelta(hours=4)))

def is_admin(sender_id):
    return sender_id == Config.ADMIN_ID

# ------------------- ПРЕДКОМПИЛИРОВАННЫЕ РЕГУЛЯРКИ -------------------
COMPILED_PATTERNS = {
    'apartment_pattern': re.compile(r"\b[1-4]\s*[+-]?\s*[1-4]\b"),
    'apartment_names': re.compile(r"\b(однушка|двушка|трёшка|трешка|четверка)\b"),
    'price_pattern': re.compile(r'\b\d+[.,]?\d*\s*(₽|руб|р\.|руbлей|доллар|\$|USD)\b'),
    'multiple_spaces': re.compile(r'\s+')
}

# ------------------- ОПТИМИЗИРОВАННЫЕ ФУНКЦИИ -------------------
async def get_chat_title(chat_entity):
    try:
        if chat_entity in chat_title_cache:
            return chat_title_cache[chat_entity]
        
        chat = await client.get_entity(chat_entity)
        title = getattr(chat, 'title', 'Unknown')
        chat_title_cache[chat_entity] = title
        return title
    except:
        return "Unknown"

def is_really_client(text: str) -> bool:
    text_lower = text.lower()
    return not any(forbidden in text_lower for forbidden in Config.ADDITIONAL_FILTERS)

def is_client_message(text: str):
    if not text or len(text.strip()) < 10:
        return False, None
    
    text_lower = text.lower()
    
    if any(bad in text_lower for bad in Config.BLACKLIST):
        return False, None
    
    if not is_really_client(text):
        return False, None
    
    has_need = any(word in text_lower for word in Config.NEED_WORDS)
    if not has_need:
        return False, None
    
    has_real_estate = any(word in text_lower for word in Config.REAL_ESTATE_WORDS)
    
    if not has_real_estate:
        if (COMPILED_PATTERNS['apartment_pattern'].search(text_lower) or 
            COMPILED_PATTERNS['apartment_names'].search(text_lower)):
            has_real_estate = True
    
    if not has_real_estate:
        return False, None
    
    if is_likely_spam(text_lower):
        return False, None
    
    found_word = next((w for w in Config.NEED_WORDS if w in text_lower), None)
    return True, found_word

def is_likely_spam(text: str) -> bool:
    if len(re.findall(r'\d', text)) > 15:
        return True
    
    if COMPILED_PATTERNS['price_pattern'].search(text):
        return True
    
    if len(text) < 50 and text.count('!') > 2:
        return True
    
    work_keywords = ["работа", "вакансия", "услуги", "мастер", "ремont", 
                    "уборка", "клининг", "сборка", "зарплата"]
    return any(word in text for word in work_keywords)

def format_message_info(chat_title, message_text, sender, found_word, message_link, message_date):
    first_name = getattr(sender, 'first_name', 'Неизвестно')
    username = getattr(sender, 'username', None)
    
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=timezone.utc)
    georgia_time = message_date.astimezone(timezone(timedelta(hours=4)))
    date_str = georgia_time.strftime("%d.%m.%Y %H:%M")
    
    cleaned_text = COMPILED_PATTERNS['multiple_spaces'].sub(' ', message_text.strip())
    
    msg = (
        "🏠 <b>НОВОЕ ОБЪЯВЛЕНИЕ!</b>\n\n"
        f"📋 <b>Группа:</b> {chat_title}\n\n"
        f"🔑 <b>Ключевое слово:</b> <code>{found_word}</code>\n\n"
        f"⏰ <b>Время:</b> {date_str} (Тбилиси)\n\n"
        f"👤 <b>Автор:</b> {first_name}"
    )
    
    if username:
        msg += f" (@{username})"
    else:
        msg += " (нет username)"
    
    msg += (
        f"\n\n📝 <b>Текст:</b>\n<code>{cleaned_text[:400]}</code>"
        + (f"..." if len(cleaned_text) > 400 else "") + "\n\n"
        f"🔗 <a href=\"{message_link}\">Открыть сообщение</a>"
    )
    
    return msg

def create_message_link(chat_entity, message_id):
    try:
        if hasattr(chat_entity, 'username') and chat_entity.username:
            return f"https://t.me/{chat_entity.username}/{message_id}"
        else:
            chat_id = getattr(chat_entity, 'id', '')
            if str(chat_id).startswith("-100"):
                chat_id = str(chat_id)[4:]
            return f"https://t.me/c/{chat_id}/{message_id}"
    except:
        return ""

# ------------------- ОБРАБОТКА СООБЩЕНИЙ -------------------
async def process_message(message):
    try:
        if not message.text:
            return False
        
        text = message.text.strip()
        if not text:
            return False
        
        # Проверка времени сообщения (только свежие)
        message_time = message.date
        current_time = datetime.now(message_time.tzinfo) if message_time.tzinfo else datetime.now()
        
        if (current_time - message_time).total_seconds() > Config.MESSAGE_AGE_LIMIT_HOURS * 3600:
            return False
        
        # Проверка на дубликаты
        if db.is_message_processed(message.id, message.chat_id):
            return False
        
        db.add_processed_message(message.id, message.chat_id)
        db.increment_stat('total_scanned')
        
        # Проверка сообщения
        ok, found_word = is_client_message(text)
        if not ok:
            db.increment_stat('skipped')
            return False
        
        sender = await message.get_sender()
        if sender is None:
            return False
            
        # Проверка уникальности текста
        user_key = hash_text(f"{sender.id}_{text}")
        if db.is_user_text_exists(user_key):
            db.increment_stat('skipped')
            return False

        db.add_user_text(user_key)
        
        # Отправка сообщения
        chat_title = await get_chat_title(message.chat_id)
        message_link = create_message_link(message.chat, message.id)
        formatted_msg = format_message_info(chat_title, text, sender, found_word, message_link, message.date)
        
        await client.send_message(TARGET_CHAT_ID, formatted_msg, parse_mode="html")
        
        # Обновление статистики
        db.increment_stat('found')
        db.set_stat('last_found_time', get_georgia_time().strftime("%d.%m.%Y %H:%M"))
        
        group_stats[chat_title] += 1
        user_stats[sender.id] += 1
        
        logger.info(f"✅ НАЙДЕНО: {found_word} в {chat_title}")
        
        return True
        
    except Exception as e:
        db.increment_stat('errors')
        logger.error(f"Ошибка обработки сообщения: {e}")
        return False

@client.on(events.NewMessage)
async def handler(event):
    try:
        if event.chat_id == TARGET_CHAT_ID:
            return

        if not (event.is_group or event.is_channel):
            return
        
        await process_message(event.message)
    except Exception as e:
        logger.error(f"Ошибка в обработчике: {e}")

# ------------------- КОМАНДЫ БОТА -------------------
@client.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    try:
        if is_admin(event.sender_id):
            uptime = datetime.now() - start_time
            hours, remainder = divmod(uptime.total_seconds(), 3600)
            minutes = remainder // 60
            
            welcome_msg = (
                "🤖 <b>🏠 БОТ МОНИТОРИНГА НЕДВИЖИМОСТИ 24/7</b>\n\n"
                "✨ <i>Система работает в режиме реального времени</i>\n\n"
                f"⏰ <b>Время:</b> {get_georgia_time().strftime('%d.%m.%Y %H:%M')} (Тбилиси)\n"
                f"🔄 <b>Аптайм:</b> {int(hours)}ч {int(minutes)}м\n"
                f"📊 <b>Статус:</b> {monitoring_status}\n\n"
                f"📨 <b>Проверено сообщений:</b> {db.get_stat('total_scanned')}\n"
                f"✅ <b>Найдено объявлений:</b> {db.get_stat('found')}\n"
                f"🔍 <b>Последняя находка:</b> {db.get_stat('last_found_time', 'Нет')}\n\n"
                "⚡ <b>Используйте /admin для управления</b>"
            )
        else:
            welcome_msg = (
                "🏠 <b>Бот мониторинга недвижимости Тбилиси</b>\n\n"
                "🔍 <b>Что я умею:</b>\n"
                "• Мониторю группы по недвижимости 24/7\n"
                "• Ищу клиентов, которые ищут жилье\n"
                "• Автоматически фильтрую объявления\n\n"
                f"📊 <b>Обработано объявлений:</b> {db.get_stat('total_scanned')}\n"
                f"✅ <b>Найдено клиентов:</b> {db.get_stat('found')}\n\n"
                "💡 <b>Для сотрудничества:</b> Обратитесь к администратору"
            )
        
        await event.respond(welcome_msg, parse_mode="html")
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")

@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    try:
        if not is_admin(event.sender_id):
            await event.respond("⚠️ <b>Доступ запрещен</b>", parse_mode="html")
            return

        buttons = [
            [Button.inline("📊 Статистика", b"stats"), Button.inline("🔄 Статус", b"status")],
            [Button.inline("📈 Топ групп", b"graph_groups"), Button.inline("👥 Пользователи", b"users")],
            [Button.inline("🔄 Обновить", b"refresh"), Button.inline("🆘 Помощь", b"help")]
        ]

        await event.respond(
            f"🎛️ <b>⚙️ АДМИН-ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n"
            f"📊 <b>Режим работы:</b> {monitoring_status}\n"
            f"⏰ <b>Время:</b> {get_georgia_time().strftime('%d.%m.%Y %H:%M')}\n"
            f"✅ <b>Найдено всего:</b> {db.get_stat('found')} объявлений\n"
            f"📨 <b>Проверено:</b> {db.get_stat('total_scanned')} сообщений\n\n"
            "📋 <b>Выберите действие:</b>",
            buttons=buttons, 
            parse_mode="html"
        )
    except Exception as e:
        logger.error(f"Ошибка в /admin: {e}")

@client.on(events.CallbackQuery)
async def callback_handler(event):
    try:
        if not is_admin(event.sender_id):
            await event.answer("⚠️ Доступ запрещен", alert=True)
            return
        
        data = event.data
        georgia_time = get_georgia_time().strftime("%d.%m.%Y %H:%M")
        
        if data == b'stats':
            uptime = datetime.now() - start_time
            hours, remainder = divmod(uptime.total_seconds(), 3600)
            minutes = remainder // 60
            
            msg = (
                "📊 <b>📈 ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
                f"⏰ <b>Время:</b> {georgia_time}\n"
                f"🔄 <b>Аптайм:</b> {int(hours)}ч {int(minutes)}м\n"
                f"📊 <b>Статус:</b> {monitoring_status}\n\n"
                f"📨 <b>Проверено сообщений:</b> {db.get_stat('total_scanned')}\n"
                f"✅ <b>Найдено объявлений:</b> {db.get_stat('found')}\n"
                f"⏭️ <b>Пропущено:</b> {db.get_stat('skipped')}\n"
                f"❌ <b>Ошибок:</b> {db.get_stat('errors')}\n\n"
                f"🔍 <b>Последняя находка:</b> {db.get_stat('last_found_time', 'Нет')}"
            )
            await event.edit(msg, parse_mode="html")
            
        elif data == b'status':
            msg = (
                "🟢 <b>📡 СТАТУС СИСТЕМЫ</b>\n\n"
                f"⏰ <b>Время:</b> {georgia_time}\n"
                f"📊 <b>Статус:</b> {monitoring_status}\n\n"
                f"📨 <b>Сообщений проверено:</b> {db.get_stat('total_scanned')}\n"
                f"✅ <b>Объявлений найдено:</b> {db.get_stat('found')}\n"
                f"👤 <b>Уникальных отправителей:</b> {len(user_stats)}\n"
                f"🏠 <b>Активных групп:</b> {len(group_stats)}\n\n"
                "💡 <b>Система работает в режиме реального времени</b>"
            )
            await event.edit(msg, parse_mode="html")
            
        elif data == b'graph_groups':
            if not group_stats:
                await event.answer("⚠️ Нет данных для графика", alert=True)
                return
            
            plt.figure(figsize=(10, 6))
            top_groups = group_stats.most_common(5)
                
            labels, values = zip(*top_groups)
            
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#F9A602', '#9BE564']
            bars = plt.bar(range(len(labels)), values, color=colors[:len(labels)])
            
            plt.xticks(range(len(labels)), labels, rotation=45, ha='right')
            plt.ylabel("Количество найденных объявлений")
            plt.title("📈 ТОП-5 ГРУПП ПО НАЙДЕННЫМ ОБЪЯВЛЕНИЯМ")
            
            for i, (bar, value) in enumerate(zip(bars, values)):
                plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                        f'{value}', ha='center', va='bottom', fontweight='bold')
            
            plt.tight_layout()
            
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
            buf.seek(0)
            plt.close()
            
            await client.send_file(event.chat_id, buf, caption="📊 <b>Топ групп по найденным объявлениям</b>", parse_mode="html")
            await event.answer("✅ График отправлен")
            
        elif data == b'users':
            if not user_stats:
                await event.answer("⚠️ Нет данных о пользователях", alert=True)
                return
            
            top_users = user_stats.most_common(10)
            users_list = "👥 <b>ТОП-10 ОТПРАВИТЕЛЕЙ:</b>\n\n"
            
            for i, (user_id, count) in enumerate(top_users, 1):
                users_list += f"{i}. ID {user_id}: {count} объявлений\n"
            
            await event.edit(users_list, parse_mode="html")
            
        elif data == b'refresh':
            await admin_panel(event)
            await event.answer("🔄 Панель обновлена")
            
        elif data == b'help':
            help_msg = (
                "🆘 <b>❓ ПОМОЩЬ ПО КОМАНДАМ</b>\n\n"
                "• /start - Информация о боте\n"
                "• /admin - Панель управления\n\n"
                "📋 <b>Кнопки админ-панели:</b>\n"
                "• 📊 Статистика - Детальная статистика\n"
                "• 🔄 Статус - Текущий статус системы\n"
                "• 📈 Топ групп - График активности\n"
                "• 👥 Пользователи - Топ отправителей\n"
                "• 🔄 Обновить - Обновить панель\n"
                "• 🆘 Помощь - Эта справка\n\n"
                "💡 <b>Как работает бот:</b>\n"
                "• 🎯 Мониторит группы 24/7\n"
                "• 🔍 Ищет клиентов недвижимости\n"
                "• 📨 Пересылает в целевой чат\n\n"
                "⏰ <b>Время работы:</b> Круглосуточно\n"
                "📍 <b>Часовой пояс:</b> Тбилиси (UTC+4)"
            )
            await event.edit(help_msg, parse_mode="html")
            
        else:
            await event.answer("⚠️ Функция в разработке", alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        await event.answer("⚠️ Произошла ошибка", alert=True)

# ------------------- ЗАПУСК БОТА -------------------
async def main():
    global TARGET_CHAT_ID
    
    try:
        # Подключаемся к Telegram
        await client.start(bot_token=Config.BOT_TOKEN)
        logger.info("🚀 Бот мониторинга запущен!")
        
        # Устанавливаем целевой чат
        entity = await client.get_entity(Config.TARGET_CHAT)
        TARGET_CHAT_ID = entity.id
        logger.info(f"✅ TARGET_CHAT_ID установлен: {TARGET_CHAT_ID}")
        
        # Отправляем приветственное сообщение
        await client.send_message(
            Config.ADMIN_ID, 
            "🎉 <b>🤖 БОТ УСПЕШНО ЗАПУЩЕН!</b>\n\n"
            "✨ <b>Система мониторинга недвижимости активирована</b>\n\n"
            "📋 <b>Режим работы:</b> 24/7 реальное время\n"
            "🎯 <b>Мониторинг:</b> Все группы с недвижимостью\n"
            "⏰ <b>Фильтрация:</b> Только свежие объявления\n\n"
            f"🕒 <b>Время запуска:</b> {get_georgia_time().strftime('%d.%m.%Y %H:%M')}\n"
            "📍 <b>Часовой пояс:</b> Тбилиси (UTC+4)\n\n"
            "💡 <b>Используйте /admin для управления</b>",
            parse_mode="html"
        )
        
        logger.info("✅ Бот перешел в режим мониторинга 24/7")
        
        # Запускаем прослушивание событий
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}. Перезапуск через 30 секунд...")
        await asyncio.sleep(30)
        await main()

if __name__ == "__main__":
    print("🎯 " + "="*50)
    print("🤖 ЗАПУСК БОТА МОНИТОРИНГА НЕДВИЖИМОСТИ 24/7")
    print("🎯 " + "="*50)
    print("📍 Режим: Реальное время")
    print("⏰ Мониторинг: Круглосуточный")
    print("🏠 Часовой пояс: Тбилиси (UTC+4)")
    print("📊 Используйте /admin для управления")
    print("🎯 " + "="*50)
    
    # Запускаем бота
    asyncio.run(main())
