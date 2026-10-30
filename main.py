import telebot
from telebot import types, apihelper
import sqlite3
import random
import string
import time

# --- НАСТРОЙКА SHUZAGRAM ---
apihelper.API_URL = "https://api.shuzagram.com/bot{0}/{1}"

TOKEN = "1780243515:e3EpKn2PnskU0FOs5bCOu275SpVBiEoTgRz"
ADMIN_ID = 1780243488

bot = telebot.TeleBot(TOKEN)
DB_PATH = "wallet.db"

# --- БАЗА ДАННЫХ ---
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, address TEXT UNIQUE, 
            is_verified INTEGER DEFAULT 0, reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Добавлено поле pool (капитализация в звёздах) и supply (кол-во монет)
        c.execute("""CREATE TABLE IF NOT EXISTS coins (
            id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER, 
            name TEXT, ticker TEXT UNIQUE, supply INTEGER DEFAULT 0, pool INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS assets (
            user_id INTEGER, ticker TEXT, amount INTEGER DEFAULT 0, 
            PRIMARY KEY (user_id, ticker)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sender_address TEXT, 
            receiver_address TEXT, ticker TEXT, amount INTEGER, 
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Стейкинг
        c.execute("""CREATE TABLE IF NOT EXISTS stakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            ticker TEXT, amount INTEGER, start_time INTEGER, 
            unlock_time INTEGER, is_active INTEGER DEFAULT 1
        )""")
        # Выводы звёзд (для админа)
        c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            amount INTEGER, status TEXT DEFAULT 'pending', 
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # Создаем монету BASE для админа, если её нет
        c.execute("SELECT 1 FROM coins WHERE ticker = 'BASE'")
        if not c.fetchone():
            c.execute("INSERT INTO coins (creator_id, name, ticker, supply, pool) VALUES (?, 'Base Coin', 'BASE', 0, 0)", (ADMIN_ID,))
        conn.commit()

# --- ХЕЛПЕРЫ ---
def get_user(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

def create_user(user_id, username):
    address = "WLT" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, address) VALUES (?, ?, ?)", (user_id, username, address))
        conn.commit()

def get_balance(user_id, ticker="BASE"):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT amount FROM assets WHERE user_id = ? AND ticker = ?", (user_id, ticker))
        row = c.fetchone()
        return row[0] if row else 0

def change_balance(user_id, ticker, amount):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO assets (user_id, ticker, amount) VALUES (?, ?, ?)
            ON CONFLICT(user_id, ticker) DO UPDATE SET amount = amount + excluded.amount""", (user_id, ticker, amount))
        conn.commit()

def get_stars_balance():
    # Заглушка для баланса звёзд бота (в реальности нужно тянуть через API ShuzaGram)
    # Мы будем эмулировать, что у бота есть звёзды, и админ может их выводить.
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT SUM(amount) FROM assets WHERE ticker = 'STARS'")
        row = c.fetchone()
        return row[0] if row[0] else 0

def change_stars_balance(amount):
    change_balance(ADMIN_ID, "STARS", amount)

# --- КЛАВИАТУРЫ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(
        types.KeyboardButton("👤 Профиль"), types.KeyboardButton("💸 Перевести"),
        types.KeyboardButton("🪙 Список монет"), types.KeyboardButton("➕ Создать монету"),
        types.KeyboardButton("📜 История"), types.KeyboardButton("🔒 Стейкинг"),
        types.KeyboardButton("📊 Топ"), types.KeyboardButton("ℹ️ Помощь")
    )
    return m

def admin_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("✅ Выдать верификацию", callback_data="admin_verify"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("💸 Вывод звёзд", callback_data="admin_withdraw")
    )
    return m

# --- СТАРТ ---
@bot.message_handler(commands=["start"])
def start(message):
    create_user(message.from_user.id, message.from_user.username)
    user = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"👋 Добро пожаловать в <b>Wallet</b>!\n\n"
        f"Адрес: <code>{user[2]}</code>\n"
        f"Баланс: <b>{get_balance(user[0])} BASE</b>",
        reply_markup=main_menu(), parse_mode="HTML"
    )

# --- ПРОФИЛЬ ---
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    user = get_user(message.from_user.id)
    if not user: return
    status = "✅ Верифицирован" if user[3] else "❌ Не верифицирован"
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT ticker, amount FROM assets WHERE user_id = ? AND amount > 0", (user[0],))
        assets = c.fetchall()
        
    assets_text = "\n".join([f"• {t}: {a}" for t, a in assets]) or "Нет монет"
    bot.send_message(message.chat.id, f"👤 <b>Профиль</b>\n\nID: <code>{user[0]}</code>\nАдрес: <code>{user[2]}</code>\nСтатус: {status}\n\n<b>Ваши активы:</b>\n{assets_text}", reply_markup=main_menu(), parse_mode="HTML")

# --- СПИСОК МОНЕТ ---
@bot.message_handler(func=lambda m: m.text == "🪙 Список монет")
def list_coins(message):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT ticker, name, supply, pool FROM coins")
        coins = c.fetchall()
        
    if not coins: return bot.send_message(message.chat.id, "Монет пока нет.", reply_markup=main_menu())
    
    text = "🪙 <b>Все монеты системы:</b>\n\n"
    for t, n, s, p in coins:
        text += f"<b>{n}</b> ({t})\nВсего: {s} | Капитализация: {p} ⭐\n\n"
    
    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode="HTML")

# --- ПЕРЕВОД ---
@bot.message_handler(func=lambda m: m.text == "💸 Перевести")
def transfer_start(message):
    msg = bot.send_message(message.chat.id, "Введите адрес получателя (WLT...):", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, transfer_address)

def transfer_address(message):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE address = ?", (message.text.strip(),))
        receiver = c.fetchone()
    if not receiver: return bot.send_message(message.chat.id, "❌ Адрес не найден.", reply_markup=main_menu())
    msg = bot.send_message(message.chat.id, "Введите тикер монеты:")
    bot.register_next_step_handler(msg, transfer_ticker, receiver[0])

def transfer_ticker(message, receiver_id):
    ticker = message.text.strip().upper()
    bal = get_balance(message.from_user.id, ticker)
    if bal <= 0: return bot.send_message(message.chat.id, f"❌ У вас нет {ticker}.", reply_markup=main_menu())
    msg = bot.send_message(message.chat.id, f"Введите сумму (доступно {bal}):")
    bot.register_next_step_handler(msg, transfer_amount, receiver_id, ticker)

def transfer_amount(message, receiver_id, ticker):
    try: amount = int(message.text)
    except: return bot.send_message(message.chat.id, "❌ Неверная сумма.", reply_markup=main_menu())
    if amount <= 0 or amount > get_balance(message.from_user.id, ticker):
        return bot.send_message(message.chat.id, "❌ Ошибка суммы.", reply_markup=main_menu())
        
    change_balance(message.from_user.id, ticker, -amount)
    change_balance(receiver_id, ticker, amount)
    
    sender = get_user(message.from_user.id)
    receiver = get_user(receiver_id)
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO transactions (sender_address, receiver_address, ticker, amount) VALUES (?, ?, ?, ?)", (sender[2], receiver[2], ticker, amount))
        conn.commit()
        
    bot.send_message(message.chat.id, f"✅ Переведено {amount} {ticker} на {receiver[2]}.", reply_markup=main_menu())
    try: bot.send_message(receiver_id, f"💰 Вы получили {amount} {ticker} от {sender[2]}!")
    except: pass

# --- СОЗДАНИЕ МОНЕТЫ ---
@bot.message_handler(func=lambda m: m.text == "➕ Создать монету")
def create_coin_start(message):
    user = get_user(message.from_user.id)
    if not user or not user[3]:
        return bot.send_message(message.chat.id, "❌ Только для верифицированных.", reply_markup=main_menu())
    msg = bot.send_message(message.chat.id, "Введите название монеты:")
    bot.register_next_step_handler(msg, create_coin_name)

def create_coin_name(message):
    msg = bot.send_message(message.chat.id, "Введите тикер (до 5 символов):")
    bot.register_next_step_handler(msg, create_coin_ticker, message.text.strip())

def create_coin_ticker(message, name):
    ticker = message.text.strip().upper()
    if len(ticker) > 5: return bot.send_message(message.chat.id, "❌ Тикер слишком длинный.", reply_markup=main_menu())
    msg = bot.send_message(message.chat.id, "Введите капитализацию (в звёздах, минимум 500 ⭐):")
    bot.register_next_step_handler(msg, create_coin_pay, name, ticker)

def create_coin_pay(message, name, ticker):
    try: pool = int(message.text)
    except: return bot.send_message(message.chat.id, "❌ Неверная сумма.", reply_markup=main_menu())
    
    total_cost = 500 + pool # 500 за создание + капитализация
    if pool < 0: return bot.send_message(message.chat.id, "❌ Ошибка суммы.", reply_markup=main_menu())

    # Тут мы создаем инвойс для оплаты
    # В реальности нужно отправлять инвойс, а по successful_payment создавать монету.
    # Для упрощения симулируем успешную оплату.
    msg = bot.send_message(message.chat.id, f"💳 К оплате: {total_cost} ⭐\n(500 за создание + {pool} в пул капитализации).\n\nОплата подтверждена (эмуляция)!")
    
    # Создаем монету
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO coins (creator_id, name, ticker, supply, pool) VALUES (?, ?, ?, 0, ?)", (message.from_user.id, name, ticker, pool))
            conn.commit()
        # Начисляем создателю монеты (пул / 1 монета = 1 звезда)
        change_balance(message.from_user.id, ticker, pool)
        bot.send_message(message.chat.id, f"✅ Монета <b>{name}</b> ({ticker}) создана!\nВам начислено {pool} {ticker} (по 1 ⭐ за монету).", reply_markup=main_menu(), parse_mode="HTML")
    except sqlite3.IntegrityError:
        bot.send_message(message.chat.id, "❌ Такой тикер уже существует.", reply_markup=main_menu())

# --- ИСТОРИЯ ---
@bot.message_handler(func=lambda m: m.text == "📜 История")
def history(message):
    user = get_user(message.from_user.id)
    if not user: return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT sender_address, receiver_address, ticker, amount, timestamp FROM transactions WHERE sender_address = ? OR receiver_address = ? ORDER BY id DESC LIMIT 10", (user[2], user[2]))
        txs = c.fetchall()
    if not txs: return bot.send_message(message.chat.id, "История пуста.", reply_markup=main_menu())
    
    text = "📜 <b>Последние 10 транзакций:</b>\n\n"
    for s, r, t, a, ts in txs:
        direction = "📤" if s == user[2] else "📥"
        text += f"{direction} {a} {t}\n<code>{s} -> {r}</code>\n{ts}\n\n"
    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode="HTML")

# --- СТЕЙКИНГ (3% в день) ---
@bot.message_handler(func=lambda m: m.text == "🔒 Стейкинг")
def staking_menu(message):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("📥 Заморозить", callback_data="stake_lock"),
        types.InlineKeyboardButton("📤 Разморозить", callback_data="stake_unlock"),
        types.InlineKeyboardButton("👀 Мои заморозки", callback_data="stake_list")
    )
    bot.send_message(message.chat.id, "🔒 <b>Стейкинг</b>\nЗаморозьте монеты на 1 день и получите 3% сверху!", reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("stake_"))
def stake_callback(call):
    if call.data == "stake_lock":
        msg = bot.send_message(call.message.chat.id, "Введите тикер монеты:")
        bot.register_next_step_handler(msg, stake_lock_ticker)
    elif call.data == "stake_unlock":
        unlock_stakes(call.message.chat.id, call.from_user.id)
    elif call.data == "stake_list":
        list_stakes(call.message.chat.id, call.from_user.id)
    bot.answer_callback_query(call.id)

def stake_lock_ticker(message):
    ticker = message.text.strip().upper()
    bal = get_balance(message.from_user.id, ticker)
    if bal <= 0: return bot.send_message(message.chat.id, f"❌ У вас нет {ticker}.", reply_markup=main_menu())
    msg = bot.send_message(message.chat.id, f"Введите сумму (доступно {bal}):")
    bot.register_next_step_handler(msg, stake_lock_amount, ticker)

def stake_lock_amount(message, ticker):
    try: amount = int(message.text)
    except: return bot.send_message(message.chat.id, "❌ Неверная сумма.", reply_markup=main_menu())
    if amount <= 0 or amount > get_balance(message.from_user.id, ticker):
        return bot.send_message(message.chat.id, "❌ Ошибка суммы.", reply_markup=main_menu())
    
    unlock_time = int(time.time()) + 86400 # 1 день
    change_balance(message.from_user.id, ticker, -amount)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO stakes (user_id, ticker, amount, start_time, unlock_time) VALUES (?, ?, ?, ?, ?)", 
                  (message.from_user.id, ticker, amount, int(time.time()), unlock_time))
        conn.commit()
    bot.send_message(message.chat.id, f"✅ Заморожено {amount} {ticker} на 1 день. Через день вы получите {int(amount * 1.03)} (с бонусом 3%).", reply_markup=main_menu())

def list_stakes(chat_id, uid):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, ticker, amount, unlock_time FROM stakes WHERE user_id = ? AND is_active = 1", (uid,))
        rows = c.fetchall()
    if not rows: return bot.send_message(chat_id, "У вас нет активных заморозок.")
    text = "🔒 <b>Ваши заморозки:</b>\n\n"
    for i, t, a, ut in rows:
        left = max(0, ut - int(time.time()))
        text += f"ID {i}: {a} {t} (осталось {left//3600} ч.)\n"
    bot.send_message(chat_id, text, parse_mode="HTML")

def unlock_stakes(chat_id, uid):
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, ticker, amount, unlock_time FROM stakes WHERE user_id = ? AND is_active = 1", (uid,))
        rows = c.fetchall()
        
        unlocked = 0
        for i, t, a, ut in rows:
            if now >= ut:
                c.execute("UPDATE stakes SET is_active = 0 WHERE id = ?", (i,))
                change_balance(uid, t, int(a * 1.03)) # +3% бонус
                unlocked += 1
        conn.commit()
        
    if unlocked > 0:
        bot.send_message(chat_id, f"✅ Разморожено и начислено {unlocked} стейков с бонусом 3%!", reply_markup=main_menu())
    else:
        bot.send_message(chat_id, "⏳ Пока нет стейков, готовых к разморозке.", reply_markup=main_menu())

# --- ТОП ---
@bot.message_handler(func=lambda m: m.text == "📊 Топ")
def top_users(message):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM assets WHERE ticker = 'BASE' ORDER BY amount DESC LIMIT 5")
        rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "Топ пуст.", reply_markup=main_menu())
    
    text = "📊 <b>Топ 5 по BASE:</b>\n\n"
    for i, (uid, amt) in enumerate(rows, 1):
        u = get_user(uid)
        un = f"@{u[1]}" if u and u[1] else f"ID: {uid}"
        text += f"{i}. {un} — <b>{amt} BASE</b>\n"
    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode="HTML")

# --- ПОМОЩЬ ---
@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def help_menu(message):
    bot.send_message(message.chat.id, "ℹ️ <b>Помощь</b>\n\n💸 Перевести — отправить монеты.\n🪙 Список монет — все монеты.\n➕ Создать монету — 500 ⭐ + капитализация.\n📜 История — последние транзакции.\n🔒 Стейкинг — 3% в день.\n📊 Топ — лучшие кошельки.\n\nВерификацию выдает админ.", reply_markup=main_menu(), parse_mode="HTML")

# --- АДМИНКА ---
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, f"🛠 <b>Админ-панель</b>\nБаланс звёзд: {get_stars_balance()} ⭐", reply_markup=admin_menu(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callback(call):
    if call.from_user.id != ADMIN_ID: return bot.answer_callback_query(call.id, "Нет доступа")
    
    if call.data == "admin_verify":
        msg = bot.send_message(call.message.chat.id, "Введите ID пользователя:")
        bot.register_next_step_handler(msg, admin_verify_user)
    elif call.data == "admin_stats":
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users"); u = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM coins"); co = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM transactions"); t = c.fetchone()[0]
        bot.send_message(call.message.chat.id, f"📊 Юзеров: {u}\nМонет: {co}\nТранзакций: {t}")
    elif call.data == "admin_withdraw":
        # Вывод звёзд (симуляция)
        stars = get_stars_balance()
        if stars <= 0: return bot.answer_callback_query(call.id, "Нет звёзд для вывода", show_alert=True)
        msg = bot.send_message(call.message.chat.id, f"Доступно: {stars} ⭐. Введите сумму для вывода:")
        bot.register_next_step_handler(msg, admin_withdraw_process)
    bot.answer_callback_query(call.id)

def admin_verify_user(message):
    try:
        uid = int(message.text.strip())
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (uid,))
            conn.commit()
        if c.rowcount > 0:
            bot.send_message(message.chat.id, f"✅ Пользователь {uid} верифицирован.")
            try: bot.send_message(uid, "🎉 Вы получили статус Верифицирован!\nТеперь вы можете создавать монеты.")
            except: pass
        else: bot.send_message(message.chat.id, "❌ Не найден.")
    except: bot.send_message(message.chat.id, "❌ Ошибка ID.")

def admin_withdraw_process(message):
    try: amt = int(message.text)
    except: return bot.send_message(message.chat.id, "❌ Неверная сумма.")
    if amt <= 0 or amt > get_stars_balance(): return bot.send_message(message.chat.id, "❌ Ошибка суммы.")
    
    change_stars_balance(-amt)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)", (ADMIN_ID, amt))
        w_id = c.lastrowid
        conn.commit()
        
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("❌ Отменить транзакцию", callback_data=f"cancel_wd_{w_id}"))
    bot.send_message(message.chat.id, f"💸 Вывод {amt} ⭐ инициирован. Ожидайте зачисления.\nID: {w_id}", reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_wd_"))
def cancel_withdraw(call):
    if call.from_user.id != ADMIN_ID: return
    w_id = int(call.data.split("_")[2])
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT amount FROM withdrawals WHERE id = ? AND status = 'pending'", (w_id,))
        row = c.fetchone()
        if not row: return bot.answer_callback_query(call.id, "Транзакция уже завершена или не найдена", show_alert=True)
        
        c.execute("UPDATE withdrawals SET status = 'cancelled' WHERE id = ?", (w_id,))
        conn.commit()
        
    change_stars_balance(row[0])
    bot.edit_message_text(f"❌ Вывод {row[0]} ⭐ отменён. Звёзды возвращены.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Вывод отменён")

db_init()
print("Бот Wallet запущен!")
bot.infinity_polling()
