from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, InlineQueryHandler, CallbackContext, CallbackQueryHandler
import sqlite3
from sqlite3 import Error
import sys

def create_database(dbname):
    conn = None
    try:
        conn = sqlite3.connect(dbname)
        ensure_tables_existance(conn)
    finally:
        if conn:
            conn.close()

def ensure_tables_existance(conn):
    statements = ["""
        CREATE TABLE IF NOT EXISTS plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            creatorUserId INTEGER NOT NULL,
            question TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS options(
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            planId INTEGER NOT NULL,
            option TEXT NOT NULL,
            FOREIGN KEY (planId) REFERENCES plans (id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS answers(
            optionId INTEGER NOT NULL,
            answeringUserId INTEGER NOT NULL,
            answer INTEGER NOT NULL,
            FOREIGN KEY (optionId) REFERENCES options (id)
        );
        """]
    for statement in statements:
        conn.cursor().execute(statement)

async def start(update: Update, context : ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(update.effective_chat.id, "Hey! This bot doesn't do anything yet.")

async def inline(update: Update, context : ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    results = [
        InlineQueryResultArticle(
            id = "FirstOption", 
            title = "First option", 
            input_message_content = InputTextMessageContent("This is a sample survey"), 
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Option 1", callback_data="1")], [InlineKeyboardButton("Option 2", callback_data="2")]])
            )
    ]
    await context.bot.answer_inline_query(update.inline_query.id, results)

async def inline_button(update: Update, context: CallbackContext):
    query = update.callback_query
    d = query.data
    await query.edit_message_text(f"The last selected item was {d}")
    await query.answer()

if __name__ == '__main__':
    token = sys.argv[1]
    dbname = sys.argv[2] if len(sys.argv) > 2 else "data.db"
    try:
        create_database(dbname)
    except Error as e:
        print(e)
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()

    start_h = CommandHandler('start', start)
    app.add_handler(start_h)

    inline_h = InlineQueryHandler(inline)
    app.add_handler(inline_h)

    inline_b = CallbackQueryHandler(inline_button)
    app.add_handler(inline_b)
    
    app.run_polling()