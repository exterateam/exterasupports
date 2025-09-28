# support_bot.py
import os
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# --- Загрузка .env ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

if not BOT_TOKEN:
    raise SystemExit("❌ Ошибка: нужно указать BOT_TOKEN как переменную окружения.")

# --- База данных ---
conn = sqlite3.connect("tickets.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    message TEXT,
    status TEXT DEFAULT 'open'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    sender TEXT,
    text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS bans (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()

# --- Помощники ---
def format_status(status: str) -> str:
    return "Открыт 🟢" if status == "open" else "Закрыт 🔴"

def is_banned(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM bans WHERE user_id=?", (user_id,))
    return cur.fetchone() is not None

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        text = (
            "👋 *Привет, администратор!*\n\n"
            "💼 *Команды:*\n"
            "📄 /alltickets — все тикеты\n"
            "✅ /close <id> — закрыть тикет\n"
            "💬 /reply <id> <текст> — ответить пользователю\n"
            "🚫 /ban <user_id> — забанить пользователя\n"
            "♻️ /unban <user_id> — разбанить пользователя\n"
            "📋 /banlist — список забаненных\n"
            "ℹ️ /start — инструкция\n"
        )
    else:
        text = (
            "👋 *Привет! Я бот поддержки.*\n\n"
            "📝 *Команды:*\n"
            "🆕 /new <текст> — создать тикет\n"
            "📋 /mytickets — свои тикеты\n"
            "ℹ️ /start — инструкция\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ Вы забанены и не можете создавать тикеты.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Используй: /new <текст проблемы>")
        return
    message = " ".join(context.args)
    cur.execute("INSERT INTO tickets (user_id, username, message) VALUES (?, ?, ?)",
                (user_id, update.effective_user.username, message))
    conn.commit()
    ticket_id = cur.lastrowid
    cur.execute("INSERT INTO messages (ticket_id, sender, text) VALUES (?, ?, ?)",
                (ticket_id, 'user', message))
    conn.commit()
    await update.message.reply_text(f"✅ Тикет #{ticket_id} создан!")
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id,
                                           f"🆕 Новый тикет #{ticket_id} от @{update.effective_user.username}:\n{message}")
        except Exception:
            pass

async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cur.execute("SELECT id, message, status FROM tickets WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("📭 У тебя нет тикетов.")
    else:
        text = "\n".join([f"#{tid} [{format_status(status)}] {msg}" for tid, msg, status in rows])
        await update.message.reply_text("📋 *Твои тикеты:*\n" + text, parse_mode="Markdown")

async def all_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    cur.execute("SELECT id, username, message, status FROM tickets")
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("📭 Нет тикетов.")
    else:
        text = "\n".join([f"#{tid} @{user} [{format_status(status)}] {msg}" for tid, user, msg, status in rows])
        await update.message.reply_text("📋 *Все тикеты:*\n" + text, parse_mode="Markdown")

async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Используй: /close <id>")
        return
    ticket_id = context.args[0]
    cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
    conn.commit()
    await update.message.reply_text(f"🔴 Тикет #{ticket_id} закрыт.")

async def reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Используй: /reply <id> <текст>")
        return
    ticket_id = context.args[0]
    reply_text = " ".join(context.args[1:])
    cur.execute("SELECT user_id FROM tickets WHERE id=?", (ticket_id,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("❌ Тикет не найден.")
        return
    user_id = row[0]
    try:
        await context.bot.send_message(user_id, f"💬 Ответ админа по тикету #{ticket_id}:\n{reply_text}")
    except Exception:
        await update.message.reply_text("❌ Не удалось отправить сообщение пользователю.")
        return
    cur.execute("INSERT INTO messages (ticket_id, sender, text) VALUES (?, ?, ?)",
                (ticket_id, 'admin', reply_text))
    conn.commit()
    await update.message.reply_text(f"✅ Ответ отправлен пользователю.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Используй: /ban <user_id>")
        return
    user_id = int(context.args[0])
    cur.execute("INSERT OR IGNORE INTO bans (user_id) VALUES (?)", (user_id,))
    conn.commit()
    await update.message.reply_text(f"🚫 Пользователь {user_id} забанен.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Используй: /unban <user_id>")
        return
    user_id = int(context.args[0])
    cur.execute("DELETE FROM bans WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text(f"♻️ Пользователь {user_id} разбанен.")

async def ban_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    cur.execute("SELECT user_id FROM bans")
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("📭 Список забаненных пользователей пуст.")
    else:
        text = "\n".join([f"🚫 {user_id}" for (user_id,) in rows])
        await update.message.reply_text("📋 *Забаненные пользователи:*\n" + text, parse_mode="Markdown")

# --- Запуск ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Подключение всех команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_ticket))
    app.add_handler(CommandHandler("mytickets", my_tickets))
    app.add_handler(CommandHandler("alltickets", all_tickets))
    app.add_handler(CommandHandler("close", close_ticket))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("banlist", ban_list))

    # Запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()
