import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import time
from html import escape
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    TypeHandler,
    filters,
)

from src.markup.keyboard import default_markup
from src.pkg.db import DbContext
from src.repositories.rewards import RewardsRepo
from src.repositories.tasks import TasksRepo
from src.repositories.users import UsersRepo

logger = logging.getLogger(__name__)

TASKS_BUTTON = "Текущие дейлики"
SHOP_BUTTON = "Магазин"

TASK_PREFIX = "task"
REWARD_PREFIX = "reward"

DENIED_MESSAGE = "⛔ У вас нет доступа к этому боту."

# Группа проверки доступа: чем меньше номер, тем раньше обрабатывается апдейт.
ACCESS_GROUP = -1


class Bot:
    def __init__(
        self,
        token: str,
        tasks_repo: TasksRepo,
        users_repo: UsersRepo,
        rewards_repo: RewardsRepo,
        allowed_ids: Iterable[int],
        on_shutdown: Callable[[Application], Awaitable[None]] | None = None,
    ):
        self.tasks_repo = tasks_repo
        self.users_repo = users_repo
        self.rewards_repo = rewards_repo
        self.allowed_ids = frozenset(allowed_ids)

        if not self.allowed_ids:
            raise ValueError("Allowed ids are not set: бот был бы открыт для всех")

        builder = ApplicationBuilder().token(token)
        if on_shutdown:
            builder = builder.post_shutdown(on_shutdown)

        self.app: Application = builder.build()
        self._register()

    @classmethod
    def create(cls, token: str, db: DbContext, allowed_ids: Iterable[int]) -> "Bot":
        async def on_shutdown(_: Application) -> None:
            await db.close()
            logger.info("Database pool closed")

        return cls(
            token,
            TasksRepo(db.pool),
            UsersRepo(db.pool),
            RewardsRepo(db.pool),
            allowed_ids,
            on_shutdown=on_shutdown,
        )

    def run(self) -> None:
        self.app.run_polling()

    def _register(self) -> None:
        self.app.add_handler(
            TypeHandler(Update, self._check_access),
            group=ACCESS_GROUP,
        )
        self.app.add_handlers(
            [
                CommandHandler("start", self.start),
                CommandHandler("tasks", self.get_current_tasks),
                MessageHandler(
                    filters.Text([TASKS_BUTTON]),
                    self.get_current_tasks,
                ),
                MessageHandler(
                    filters.Text([SHOP_BUTTON]),
                    self.show_rewards,
                ),
                CallbackQueryHandler(
                    self.complete_task,
                    pattern=rf"^{TASK_PREFIX}:\d+$",
                ),
                CallbackQueryHandler(
                    self.buy_reward,
                    pattern=rf"^{REWARD_PREFIX}:\d+$",
                ),
            ]
        )

    async def _check_access(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Пропускает дальше только разрешённых пользователей.

        Отрабатывает раньше остальных хендлеров, поэтому чужой апдейт до бизнес-логики
        и до базы не доходит.
        """
        user = update.effective_user
        if user and user.id in self.allowed_ids:
            return

        logger.warning(
            "access denied: user=%s chat=%s update=%s",
            user.id if user else None,
            update.effective_chat.id if update.effective_chat else None,
            update.update_id,
        )

        if update.callback_query:
            await update.callback_query.answer(DENIED_MESSAGE, show_alert=True)
        elif update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=DENIED_MESSAGE,
            )

        raise ApplicationHandlerStop

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        name = f"daily-{chat_id}"

        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

        notification_time = time(hour=20, minute=0, tzinfo=ZoneInfo("Europe/Moscow"))
        context.job_queue.run_daily(self.daily_checkup, time=notification_time, chat_id=update.effective_chat.id)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Бот запущен!",
            reply_markup=default_markup,
        )


    async def daily_checkup(self, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_message(chat_id=context.job.chat_id, text="Не забудь отметить дейлики🔔")

    async def get_current_tasks(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        tasks = await self.tasks_repo.get_tasks()

        if not tasks:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🎉 Дейликов пока нет — можно отдыхать!",
            )
            return

        balance = await self.users_repo.get_balance(update.effective_user.id) or 0

        lines = [
            f"{'✅' if task.completed else '▫️'} {escape(task.text)}  "
            f"<b>+{task.reward_points}</b>"
            for task in tasks
        ]
        text = (
            "📋 <b>Текущие дейлики</b>\n"
            f"💰 Баланс: <b>{balance}</b>\n\n"
            + "\n".join(lines)
            + "\n\n<i>Нажми на кнопку, чтобы отметить выполненное</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✅' if task.completed else '▫️'} {task.text} · +{task.reward_points}",
                    callback_data=f"{TASK_PREFIX}:{task.task_id}",
                )
            ]
            for task in tasks
        ]

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def complete_task(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        tg_id = update.effective_user.id
        task_id = int(query.data.removeprefix(f"{TASK_PREFIX}:"))
        task = await self.tasks_repo.get_task_by_id(task_id)

        balance = await self.users_repo.get_balance(tg_id)
        balance += task.reward_points
        await self.users_repo.update_balance(tg_id=tg_id, amount=balance)

        logger.info("user=%s task=%s balance=%s", tg_id, task.task_id, balance)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"✅ <b>{escape(task.text)}</b>\n"
                f"+{task.reward_points} баллов · 💰 Баланс: <b>{balance}</b>"
            ),
            parse_mode=ParseMode.HTML,
        )

    async def show_rewards(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        rewards = await self.rewards_repo.get_rewards()

        if not rewards:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🏪 В магазине пока пусто.",
            )
            return

        balance = await self.users_repo.get_balance(update.effective_user.id) or 0

        lines = [
            f"{'🟢' if balance >= reward.cost else '🔒'} {escape(reward.name)}  "
            f"<b>{reward.cost}</b>"
            for reward in rewards
        ]
        text = f"🏪 <b>Магазин</b>\n💰 Баланс: <b>{balance}</b>\n\n" + "\n".join(lines)

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'🟢' if balance >= reward.cost else '🔒'} {reward.name} · {reward.cost}",
                    callback_data=f"{REWARD_PREFIX}:{reward.reward_id}",
                )
            ]
            for reward in rewards
        ]

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def buy_reward(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query

        tg_id = update.effective_user.id
        reward_id = int(query.data.removeprefix(f"{REWARD_PREFIX}:"))
        reward = await self.rewards_repo.get_reward_by_id(reward_id)

        balance = await self.users_repo.spend_points(tg_id=tg_id, amount=reward.cost)

        if balance is None:
            current = await self.users_repo.get_balance(tg_id) or 0
            await query.answer(
                f"Не хватает {reward.cost - current} баллов на «{reward.name}»",
                show_alert=True,
            )
            return

        await query.answer()

        logger.info(
            "user=%s bought reward=%s cost=%s balance=%s",
            tg_id,
            reward.reward_id,
            reward.cost,
            balance,
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"🎁 Куплено: <b>{escape(reward.name)}</b>\n"
                f"−{reward.cost} баллов · 💰 Баланс: <b>{balance}</b>"
            ),
            parse_mode=ParseMode.HTML,
        )
