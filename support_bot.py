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
conn.commit()

# --- Помощник для статусов ---
def format_status(status: str) -> str:
    if status == "open":
        return "Открыт 🟢"
    elif status == "closed":
        return "Закрыт 🔴"
    else:
        return status

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        text = (
            "👋 *Привет, администратор!*\n\n"
            "*Команды для управления тикетами:*\n"
            "📄 /alltickets — показать все тикеты\n"
            "✅ /close <id> — закрыть тикет\n"
            "*Команды для пользователей:*\n"
            "🆕 /new <текст> — создать новый тикет\n"
            "📋 /mytickets — посмотреть свои тикеты\n"
            "ℹ️ /start — показать эту инструкцию\n"
        )
    else:
        text = (
            "👋 *Привет! Я бот поддержки.*\n\n"
            "📝 *Команды для пользователей:*\n"
            "🆕 /new <текст> — создать новый тикет\n"
            "📋 /mytickets — посмотреть свои тикеты\n"
            "ℹ️ /start — показать эту инструкцию\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Напиши описание: /new <текст проблемы>")
        return
    message = " ".join(context.args)
    cur.execute("INSERT INTO tickets (user_id, username, message) VALUES (?, ?, ?)",
                (update.effective_user.id, update.effective_user.username, message))
    conn.commit()
    ticket_id = cur.lastrowid
    await update.message.reply_text(f"✅ Тикет #{ticket_id} создан!")
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id,
                                           f"🆕 Новый тикет #{ticket_id} от @{update.effective_user.username}:\n{message}")
        except Exception:
            pass

async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT id, message, status FROM tickets WHERE user_id=?", (update.effective_user.id,))
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

# --- Запуск ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_ticket))
    app.add_handler(CommandHandler("mytickets", my_tickets))
    app.add_handler(CommandHandler("alltickets", all_tickets))
    app.add_handler(CommandHandler("close", close_ticket))

    app.run_polling()

if __name__ == "__main__":
    main()
