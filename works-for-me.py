from telegram import CallbackQuery, Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, InlineQueryHandler, CallbackContext, CallbackQueryHandler, Application, filters
import sqlite3
from sqlite3 import Error
import sys

class Repository:
    dbname: str = None
    def __init__(self, dbname):
        self.dbname = dbname
    @staticmethod
    def dict_factory(cursor: sqlite3.Cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d
    def connect(self):
        conn = sqlite3.connect(self.dbname)
        conn.row_factory = Repository.dict_factory
        return conn
    def create_database(self):
        conn = None
        try:
            conn = self.connect()
            Repository.ensure_tables_existance(conn)
        finally:
            if conn:
                conn.close()
    @staticmethod
    def ensure_tables_existance(conn):
        statements = ["""
            CREATE TABLE IF NOT EXISTS plans(
                creatorUserId INTEGER NOT NULL,
                question TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS options(
                planId INTEGER NOT NULL,
                option TEXT NOT NULL,
                FOREIGN KEY (planId) REFERENCES plans (rowid)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS answers(
                optionId INTEGER NOT NULL,
                answeringUserId INTEGER NOT NULL,
                answer INTEGER NOT NULL,
                FOREIGN KEY (optionId) REFERENCES options (rowid)
            );
            """]
        for statement in statements:
            conn.cursor().execute(statement)
    def get_plan(self, planid, userid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT rowid, creatorUserId, question FROM plans WHERE creatorUserId = ? AND rowid = ?", (userid,planid,))
            rows = cursor.fetchone()
            return rows
        except Error as e:
            pass
        finally:
            conn.close()
    def get_all_plans(self, userId):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT rowid, question FROM plans WHERE creatorUserId = ?", (userId,))
            rows = cursor.fetchall()
            return rows
        finally:
            conn.close()
    def get_all_options(self, planid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT rowid, planid, option FROM options WHERE planid = ?", (planid,))
            return cursor.fetchall()
        finally:
            conn.close()
    def insert_fake_plan(self, userid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("INSERT INTO plans (creatorUserId, question) VALUES (?, \"When should we go to the place?\")", (userid,))
            rowid = cursor.lastrowid
            conn.cursor().execute("INSERT INTO options (planId, option) VALUES (?, \"Today\"), (?, \"Tomorrow\")", (rowid,rowid,))
            conn.commit()
        finally:
            conn.close()
    def delete_plan(self, userid, planid):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("DELETE FROM plans WHERE creatorUserId = ? AND rowid = ?", (userid, planid,))
            conn.commit()
        finally:
            conn.close()
    def remove_option(self, planid, optionid):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("DELETE FROM options WHERE planid = ? AND rowid = ?", (planid, optionid,))
            conn.commit()
        finally:
            conn.close()
    def update_plan_title(self, text, userid, planid):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("UPDATE plans SET question = ? WHERE creatorUserId = ? AND rowid = ?", (text, userid, planid,))
            conn.commit()
        finally:
            conn.close()


class Bot:
    repo: Repository = None
    app: Application = None
    user_operations = {}
    @staticmethod
    def make_plan_list_markup(userid, plans):
        return InlineKeyboardMarkup(list(map(lambda x: [InlineKeyboardButton(str(x["question"]), callback_data=f"m|{userid}|{int(x['rowid'])}")], plans)))
    async def start_or_manage(self, update: Update, context : ContextTypes.DEFAULT_TYPE):
        plans = self.repo.get_all_plans(update.effective_user.id)
        markup = Bot.make_plan_list_markup(update.effective_user.id, plans)
        await context.bot.send_message(update.effective_chat.id, "Select a plan to manage it", reply_markup=markup)

    async def fake(self, update: Update, context : ContextTypes.DEFAULT_TYPE):
        try:
            self.repo.insert_fake_plan(update.effective_user.id)
            await context.bot.send_message(update.effective_chat.id, "Fake entry created")
        except Exception as e:
            await context.bot.send_message(update.effective_chat.id, f"Failed to create fake entry: {e}")

    async def plaintext(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        op = self.user_operations.pop(update.effective_user.id, None)
        if(op):
            d = op.split('|')
            match d[0]:
                case "q":
                    userid = int(d[1])
                    planid = int(d[2])
                    await self.edit_question(update.message.text, update, context, userid, planid)
        else:
            await context.bot.send_message(update.effective_chat.id, "I'm sorry, I don't know what you mean")

    async def inline(self, update: Update, context : ContextTypes.DEFAULT_TYPE):
        query = update.inline_query.query
        results = [
            InlineQueryResultArticle(
                id = "FirstOption", 
                title = "First option", 
                input_message_content = InputTextMessageContent("This is a sample survey"), 
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Option 1", callback_data="1")], [InlineKeyboardButton("Option 2", callback_data="2")]])
                )
        ]
        await context.bot.answer_inline_query(update.inline_query.id, results, switch_pm_text="Manage your plans", switch_pm_parameter="manage")

    async def inline_button(self, update: Update, context: CallbackContext):
        query = update.callback_query
        d = str(query.data).split('|')
        match d[0]:
            case "m":
                userid = int(d[1])
                planid = int(d[2])
                await self.manage_plan(query, userid, planid)
            case "d":
                userid = int(d[1])
                planid = int(d[2])
                await self.delete_plan_confirmation(query, userid, planid)
            case "dd":
                userid = int(d[1])
                planid = int(d[2])
                await self.delete_plan(query, userid, planid)
            case "q":
                userid = int(d[1])
                planid = int(d[2])
                await self.start_question_edit(query, userid, planid)
            case "c":
                await self.cancel_operation(query)
            case "-":
                userid = int(d[1])
                planid = int(d[2])
                await self.choose_option_to_remove(query, userid, planid)
            case "--":
                planid = int(d[1])
                optionid = int(d[2])
                await self.remove_option(query, planid, optionid)
            case _:
                await query.edit_message_text("We're sorry, there was an error processing your button press")
        await query.answer()
    async def manage_plan(self, query: CallbackQuery, userid, planid):
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✍️ Edit question", callback_data=f"q|{userid}|{planid}"),
                    InlineKeyboardButton("❌ Delete", callback_data=f"d|{userid}|{planid}")
                ],
                [
                    InlineKeyboardButton("➕ Add option", callback_data=f"+|{userid}|{planid}"),
                    InlineKeyboardButton("➖ Remove option", callback_data=f"-|{userid}|{planid}")
                ],
                [InlineKeyboardButton("ℹ️ Show results", callback_data=f"r|{userid}|{planid}")]
            ])
        plan = self.repo.get_plan(planid, userid)
        await query.edit_message_text(f'Editing "{plan["question"]}"', reply_markup=reply_markup)
    async def remove_option(self, query: CallbackQuery, planid, optionid):
        self.repo.remove_option(planid, optionid)
        await query.edit_message_text("Option removed")
    async def choose_option_to_remove(self, query: CallbackQuery, userid, planid):
        plan = self.repo.get_plan(planid, userid)
        if(plan):
            options = self.repo.get_all_options(planid)
            markup_content = list(map(lambda x: [InlineKeyboardButton(f"➖ {x['option']}", callback_data=f"--|{planid}|{x['rowid']}")], options))
            markup_content.append([InlineKeyboardButton("❌ Cancel", callback_data="c")])
            reply_markup = InlineKeyboardMarkup(markup_content)
            await query.edit_message_text("What option do you want to remove?", reply_markup=reply_markup)
    async def start_question_edit(self, query: CallbackQuery, userid, planid):
        self.user_operations[userid] = f"q|{userid}|{planid}"
        plan = self.repo.get_plan(planid, userid)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="c")]])
        await query.edit_message_text(f'Ok, send me the new title for "{plan["question"]}"', reply_markup=reply_markup)
    async def edit_question(self, text, update: Update, context: ContextTypes.DEFAULT_TYPE, userid, planid):
        self.repo.update_plan_title(text, userid, planid)
        await context.bot.send_message(update.effective_chat.id, "Title changed")
    async def delete_plan_confirmation(self, query: CallbackQuery, userid, planid):
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"dd|{userid}|{planid}"),
            InlineKeyboardButton("❌ No", callback_data="c")
        ]])
        plan = self.repo.get_plan(planid, userid)
        await query.edit_message_text(f'Really delete "{plan["question"]}"?', reply_markup=reply_markup)
    async def cancel_operation(self, query: CallbackQuery):
        self.user_operations.pop(query.from_user.id, None)
        await query.edit_message_text("Ok, nevermind")
    async def delete_plan(self, query: CallbackQuery, userid, planid):
        plan = self.repo.get_plan(planid, userid)
        self.repo.delete_plan(userid, planid)
        await query.edit_message_text(f'Plan "{plan["question"]}" deleted')
    def __init__(self, token, repository):
        self.repo = repository
        self.app = ApplicationBuilder().token(token).build()
        start_h = CommandHandler('start', self.start_or_manage)
        self.app.add_handler(start_h)
        manage_h = CommandHandler('manage', self.start_or_manage)
        self.app.add_handler(manage_h)
        fake_h = CommandHandler('fake', self.fake)
        self.app.add_handler(fake_h)
        inline_h = InlineQueryHandler(self.inline)
        self.app.add_handler(inline_h)
        inline_b = CallbackQueryHandler(self.inline_button)
        self.app.add_handler(inline_b)
        plaintext_h = MessageHandler(filters.TEXT, callback=self.plaintext)
        self.app.add_handler(plaintext_h)
    def start(self):
        self.app.run_polling()
        return self.app

if __name__ == '__main__':
    token = sys.argv[1]
    dbname = sys.argv[2] if len(sys.argv) > 2 else "data.db"
    repository = Repository(dbname)
    try:
        repository.create_database()
    except Error as e:
        print(e)
        sys.exit(1)
    bot = Bot(token=token, repository=repository).start()