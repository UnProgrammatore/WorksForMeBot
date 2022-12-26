from multiprocessing import current_process
from telegram import CallbackQuery, Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, InlineQueryHandler, CallbackContext, CallbackQueryHandler, Application, filters
import sqlite3
from sqlite3 import Error
import sys
from datetime import datetime, timezone

class Repository:
    ANSWER_NO = 0
    ANSWER_YES = 1
    ANSWER_IF_NECESSARY = 2
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
                question TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                creationDate TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS options(
                planId INTEGER NOT NULL,
                option TEXT NOT NULL,
                FOREIGN KEY (planId) REFERENCES plans (rowid) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS answers(
                optionId INTEGER NOT NULL,
                answeringUserId INTEGER NOT NULL,
                answeringUserName TEXT NOT NULL,
                answer INTEGER NOT NULL,
                FOREIGN KEY (optionId) REFERENCES options (rowid) ON DELETE CASCADE
            );
            """]
        for statement in statements:
            conn.cursor().execute(statement)
    def get_option_name(self, optionid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT option FROM options WHERE rowid = ?", (optionid,))
            option = cursor.fetchone()
            if option is None:
                return None
            else:
                return option["option"]
        finally:
            conn.close()
    def get_current_vote(self, optionid, userid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT answer FROM answers WHERE optionId = ? AND answeringUserId = ?", (optionid, userid,))
            answer = cursor.fetchone()
            if answer is None:
                return None
            else:
                return answer["answer"]
        finally:
            conn.close()
    def update_vote(self, optionid, userid, vote):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("UPDATE answers SET answer = ? WHERE optionId = ? AND answeringUserId = ?", (vote, optionid, userid,))
            conn.commit()
        finally:
            conn.close()
    def insert_vote(self, optionid, userid, username, vote):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("INSERT INTO answers (optionId, answeringUserId, answeringUserName, answer) VALUES (?, ?, ?, ?)", (optionid, userid, username, vote,))
            conn.commit()
        finally:
            conn.close()
    def get_all_plans(self, userId):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT rowid, question FROM plans WHERE creatorUserId = ? AND enabled = 1", (userId,))
            rows = cursor.fetchall()
            return rows
        finally:
            conn.close()
    def get_plan(self, planid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("SELECT rowid, creatorUserId, question FROM plans WHERE rowid = ?", (planid,))
            rows = cursor.fetchone()
            return rows
        except Error as e:
            pass
        finally:
            conn.close()
    def get_plan_options_with_results(self, planid):
        conn = None
        try:
            conn = self.connect()
            options_cursor = conn.cursor().execute("""
            SELECT
                o.rowid,
                o.planId,
                o.option,
                SUM(IIF(a.answer = ?, 1, 0)) As confirmedPeopleNumber,
                SUM(IIF(a.answer = ?, 1, 0)) As maybePeopleNumber
            FROM
                options o
                LEFT JOIN answers a ON o.rowid = a.optionId
            WHERE
                o.planId = ?
            GROUP BY
                o.rowid
            """, (Repository.ANSWER_YES, Repository.ANSWER_IF_NECESSARY, planid,))
            options = options_cursor.fetchall()
            return options
        finally:
            conn.close()
    def get_all_plans_filtered(self, userId, filter, max_rows_filter):
        conn = None
        try:
            conn = self.connect()
            plan_cursor = conn.cursor().execute("SELECT rowid, question FROM plans WHERE creatorUserId = ? AND enabled = 1 AND question LIKE ? ORDER BY creationDate DESC LIMIT ?", (userId, f'%{filter}%', max_rows_filter,))
            plan_rows = plan_cursor.fetchall()
            return plan_rows
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
    def start_plan_creation(self, title, userid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("INSERT INTO plans (creatorUserId, question, enabled, creationDate) VALUES (?, ?, 0, ?)", (userid, title, datetime.now(tz=timezone.utc),))
            rowid = cursor.lastrowid
            conn.commit()
            return rowid
        finally:
            conn.close()
    def plan_ready(self, planid):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("UPDATE plans SET enabled = 1 WHERE rowid = ?", (planid,))
            conn.commit()
        finally:
            conn.close()
    def delete_plan(self, userid, planid):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("DELETE FROM answers WHERE optionId IN (SELECT rowid FROM options WHERE planId = ?)", (planid,))
            conn.cursor().execute("DELETE FROM options WHERE planId = ?", (planid,))
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
    def add_option(self, text, planid):
        conn = None
        try:
            conn = self.connect()
            conn.cursor().execute("INSERT INTO options (planId, option) VALUES (?, ?)", (planid, text,))
            conn.commit()
        finally:
            conn.close()
    def get_answers_formatted(self, planid):
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor().execute("""
            SELECT
                o.rowid,
                o.option,
                GROUP_CONCAT(IIF(a.answer = ?, a.answeringUserName, NULL), ", ") As confirmedPeople,
                SUM(IIF(a.answer = ?, 1, 0)) As confirmedPeopleNumber,
                GROUP_CONCAT(IIF(a.answer = ?, a.answeringUserName, NULL), ", ") As maybePeople,
                SUM(IIF(a.answer = ?, 1, 0)) As maybePeopleNumber
            FROM
                options o
                LEFT JOIN answers a ON o.rowid = a.optionId
            WHERE
                o.planId = ?
            GROUP BY
                o.rowid
            """, (Repository.ANSWER_YES, Repository.ANSWER_YES, Repository.ANSWER_IF_NECESSARY, Repository.ANSWER_IF_NECESSARY, planid,))
            return cursor.fetchall()
        finally:
            conn.close()


class Bot:
    repo: Repository = None
    app: Application = None
    bot_name = ""
    user_operations = {}
    @staticmethod
    def answer_to_text(answer):
        match answer:
            case Repository.ANSWER_YES:
                return "✔ Yes"
            case Repository.ANSWER_IF_NECESSARY:
                return "❔ If necessary"
            case Repository.ANSWER_NO:
                return "❌ No"
    @staticmethod
    def make_plan_list_markup(userid, plans):
        return InlineKeyboardMarkup(list(map(lambda x: [InlineKeyboardButton(str(x["question"]), callback_data=f"m|{userid}|{int(x['rowid'])}")], plans)))
    @staticmethod
    def make_option_selector_markup(options, planid, userid):
        def confirmedPeopleNumber(el):
            return int(el["confirmedPeopleNumber"])
        def maybePeopleNumber(el):
            return int(el["maybePeopleNumber"])
        option_selector_list = list(map(lambda x: [InlineKeyboardButton(f'{str(x["option"])}{f" ✔*{confirmedPeopleNumber(x)}" if confirmedPeopleNumber(x) > 0 else ""}{f" ❔*{maybePeopleNumber(x)}" if maybePeopleNumber(x) > 0 else ""}', callback_data = f"v|{planid}|{x['rowid']}")], options))
        option_selector_list.append([InlineKeyboardButton("ℹ️ Show full results", callback_data = f"rrv|{userid}|{planid}")])
        return InlineKeyboardMarkup(option_selector_list)
    @staticmethod
    def make_plan_list_expandable_inline_markup(plans):
        results = list(map(lambda x:
            InlineQueryResultArticle(
                id = x["rowid"],
                title = x["question"],
                input_message_content = InputTextMessageContent(f'Click the button below to start the poll \"{x["question"]}\"'),
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶ Start voting!", callback_data = f"s|{x['rowid']}")]])
            ), plans))
        return results
    @staticmethod
    def get_ordinal(option):
        if option == 11:
            return '11th'
        elif option == 12:
            return '12th'
        elif option == 13:
            return '13th'
        else:
            match (option % 10):
                case 1:
                    return f'{option}st'
                case 2:
                    return f'{option}nd'
                case 3:
                    return f'{option}rd'
                case _:
                    return f'{option}th'
    async def start_or_manage(self, update: Update, context : ContextTypes.DEFAULT_TYPE):
        plans = self.repo.get_all_plans(update.effective_user.id)
        if(len(plans) > 0):
            markup = Bot.make_plan_list_markup(update.effective_user.id, plans)
            await context.bot.send_message(update.effective_chat.id, "Select a plan to manage it, or send me /new to create a new one", reply_markup=markup)
        else:
            await context.bot.send_message(update.effective_chat.id, "You don't have any plan yet, send me /new to create a new one")
    async def new_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.user_operations[update.effective_user.id] = f'n|{update.effective_user.id}'
        await context.bot.send_message(update.effective_chat.id, "Ok, send me the name for the plan")
    async def done_inserting_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE, planid):
        self.repo.plan_ready(planid)
        await context.bot.send_message(update.effective_chat.id, f"Great! Your plan is ready! You can now send it to whoever you want by writing @{self.bot_name} and selecting this plan")
    async def done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        op = self.user_operations.pop(update.effective_user.id, None)
        failed_command = False
        if(op):
            d = op.split('|')
            match d[0]:
                case "++":
                    planid = int(d[1])
                    await self.done_inserting_options(update, context, planid)
                case _:
                    failed_command = True
        else:
            failed_command = True
        if(failed_command):
            await context.bot.send_message("The command /done does nothing right now")
            self.user_operations[update.effective_user.id] = op
    async def new_plan_title_sent(self, text, update: Update, context: ContextTypes.DEFAULT_TYPE, userid):
        planid = self.repo.start_plan_creation(text, userid)
        self.user_operations[update.effective_user.id] = f'++|{planid}|1'
        await context.bot.send_message(update.effective_chat.id, "Great! Now send me the 1st option, or /done to finish")
    async def new_plan_add_option(self, text, update: Update, context: ContextTypes.DEFAULT_TYPE, planid, option):
        self.repo.add_option(text, planid)
        self.user_operations[update.effective_user.id] = f'++|{planid}|{option + 1}'
        await context.bot.send_message(update.effective_chat.id, f"Ok, now send me the {Bot.get_ordinal(option + 1)}, or /done to finish")
    async def plaintext(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        op = self.user_operations.pop(update.effective_user.id, None)
        if(op):
            d = op.split('|')
            match d[0]:
                case "q":
                    userid = int(d[1])
                    planid = int(d[2])
                    await self.edit_question(update.message.text, update, context, userid, planid)
                case "+":
                    userid = int(d[1])
                    planid = int(d[2])
                    await self.add_option(update.message.text, update, context, planid)
                case "n":
                    userid = int(d[1])
                    await self.new_plan_title_sent(update.message.text, update, context, userid)
                case "++":
                    planid = int(d[1])
                    option = int(d[2])
                    await self.new_plan_add_option(update.message.text, update, context, planid, option)
        else:
            await context.bot.send_message(update.effective_chat.id, "I'm sorry, I don't know what you mean")

    async def inline(self, update: Update, context : ContextTypes.DEFAULT_TYPE):
        query = update.inline_query.query
        userid = update.inline_query.from_user.id
        plans = self.repo.get_all_plans_filtered(userid, query.strip(), 10)
        results = Bot.make_plan_list_expandable_inline_markup(plans)
        await context.bot.answer_inline_query(update.inline_query.id, results, switch_pm_text="Manage your plans or create a new one", switch_pm_parameter="manage", cache_time=0)
    async def start_poll(self, query: CallbackQuery, planid):
        plan = self.repo.get_plan(planid)
        plan_options = self.repo.get_plan_options_with_results(planid)
        option_selector = Bot.make_option_selector_markup(plan_options, planid, int(plan["creatorUserId"]))
        await query.edit_message_text(f"{plan['question']}", reply_markup=option_selector)
    async def vote(self, query: CallbackQuery, planid, optionid):
        userid = query.from_user.id
        username = query.from_user.name
        current_vote = self.repo.get_current_vote(optionid, userid)
        option = self.repo.get_option_name(optionid)
        if current_vote is None:
            new_vote = Repository.ANSWER_YES
            self.repo.insert_vote(optionid, userid, username, new_vote)
        else:
            match current_vote:
                case Repository.ANSWER_YES:
                    new_vote = Repository.ANSWER_IF_NECESSARY
                case Repository.ANSWER_IF_NECESSARY:
                    new_vote = Repository.ANSWER_NO
                case Repository.ANSWER_NO:
                    new_vote = Repository.ANSWER_YES
                case _:
                    new_vote = Repository.ANSWER_YES
            self.repo.update_vote(optionid, userid, new_vote)
        plan = self.repo.get_plan(planid)
        plan_options = self.repo.get_plan_options_with_results(planid)
        option_selector = Bot.make_option_selector_markup(plan_options, planid, int(plan["creatorUserId"]))
        await query.answer(f"You answered {Bot.answer_to_text(new_vote)} to {option}")
        await query.edit_message_text(f"{plan['question']}", reply_markup=option_selector)
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
            case "+":
                userid = int(d[1])
                planid = int(d[2])
                await self.start_add_option(query, userid, planid)
            case "r":
                userid = int(d[1])
                planid = int(d[2])
                await self.show_results(query, userid, planid)
            case "rr":
                userid = int(d[1])
                planid = int(d[2])
                await self.show_extended_results(query, userid, planid)
            case "rrv":
                userid = int(d[1])
                planid = int(d[2])
                await self.show_extended_results(query, userid, planid)
            case "s":
                planid = int(d[1])
                await self.start_poll(query, planid)
            case "v":
                planid = int(d[1])
                optionid = int(d[2])
                await self.vote(query, planid, optionid)
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
        plan = self.repo.get_plan(planid)
        await query.edit_message_text(f'Editing "{plan["question"]}"', reply_markup=reply_markup)
    async def show_results(self, query: CallbackQuery, userid, planid):
        plan = self.repo.get_plan(planid)
        results = self.repo.get_answers_formatted(planid)
        final_message = f'Here are the results for "{plan["question"]}":'
        for result in results:
            final_message += f'\n{result["option"]}: {"✔" * result["confirmedPeopleNumber"]}{"❔" * result["maybePeopleNumber"]}{"None" if result["confirmedPeopleNumber"] + result["maybePeopleNumber"] == 0 else ""}'
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("➕ More info", callback_data=f'rr|{userid}|{planid}')]])
        await query.edit_message_text(final_message, reply_markup=reply_markup)
    async def show_extended_results(self, query: CallbackQuery, userid, planid):
        plan = self.repo.get_plan(planid)
        pressing_user_id = query.from_user.id
        if(userid != pressing_user_id):
            await query.answer("Only the creator of this plan can show the results", show_alert=True)
            return
        results = self.repo.get_answers_formatted(planid)
        final_message = f'Here are the results for "{plan["question"]}":'
        for result in results:
            final_message += f'\n\n{result["option"]}:\n- {"✔ " + result["confirmedPeople"] if result["confirmedPeopleNumber"] > 0 else "No one"} confirmed their availability for this day\n- {"❔ " + result["maybePeople"] if result["maybePeopleNumber"] > 0 else "No one"} said they may be available for this day if strictly necessary'
        await query.edit_message_text(final_message)
    async def start_add_option(self, query: CallbackQuery, userid, planid):
        self.user_operations[userid] = f"+|{userid}|{planid}"
        plan = self.repo.get_plan(planid)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="c")]])
        await query.edit_message_text(f'Ok, send me the new option for "{plan["question"]}"', reply_markup=reply_markup)
    async def add_option(self, text, update: Update, context: ContextTypes.DEFAULT_TYPE, planid):
        self.repo.add_option(text, planid)
        await context.bot.send_message(update.effective_chat.id, "Option added")
    async def remove_option(self, query: CallbackQuery, planid, optionid):
        self.repo.remove_option(planid, optionid)
        await query.edit_message_text("Option removed")
    async def choose_option_to_remove(self, query: CallbackQuery, userid, planid):
        plan = self.repo.get_plan(planid)
        if(plan):
            options = self.repo.get_all_options(planid)
            markup_content = list(map(lambda x: [InlineKeyboardButton(f"➖ {x['option']}", callback_data=f"--|{planid}|{x['rowid']}")], options))
            markup_content.append([InlineKeyboardButton("❌ Cancel", callback_data="c")])
            reply_markup = InlineKeyboardMarkup(markup_content)
            await query.edit_message_text("What option do you want to remove?", reply_markup=reply_markup)
    async def start_question_edit(self, query: CallbackQuery, userid, planid):
        self.user_operations[userid] = f"q|{userid}|{planid}"
        plan = self.repo.get_plan(planid)
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
        plan = self.repo.get_plan(planid)
        await query.edit_message_text(f'Really delete "{plan["question"]}"?', reply_markup=reply_markup)
    async def cancel_operation(self, query: CallbackQuery):
        self.user_operations.pop(query.from_user.id, None)
        await query.edit_message_text("Ok, nevermind")
    async def delete_plan(self, query: CallbackQuery, userid, planid):
        plan = self.repo.get_plan(planid)
        self.repo.delete_plan(userid, planid)
        await query.edit_message_text(f'Plan "{plan["question"]}" deleted')
    def __init__(self, token, repository, bot_name):
        self.repo = repository
        self.app = ApplicationBuilder().token(token).build()
        start_h = CommandHandler('start', self.start_or_manage)
        self.app.add_handler(start_h)
        manage_h = CommandHandler('manage', self.start_or_manage)
        self.app.add_handler(manage_h)
        new_h = CommandHandler('new', self.new_plan)
        self.app.add_handler(new_h)
        done_h = CommandHandler('done', self.done)
        self.app.add_handler(done_h)
        inline_h = InlineQueryHandler(self.inline)
        self.app.add_handler(inline_h)
        inline_b = CallbackQueryHandler(self.inline_button)
        self.app.add_handler(inline_b)
        plaintext_h = MessageHandler(filters.TEXT, callback=self.plaintext)
        self.app.add_handler(plaintext_h)
        self.bot_name = bot_name
    def start(self):
        self.app.run_polling()
        return self.app

if __name__ == '__main__':
    token = sys.argv[1]
    dbname = sys.argv[2] if len(sys.argv) > 2 else "data.db"
    botname = sys.argv[3] if len(sys.argv) > 3 else "WorksForMeBot"
    repository = Repository(dbname)
    try:
        repository.create_database()
    except Error as e:
        print(e)
        sys.exit(1)
    bot = Bot(token=token, repository=repository, bot_name=botname).start()