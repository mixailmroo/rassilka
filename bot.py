"""
fe|AutoSender — Telegram рассылка-бот
Полная копия с поддержкой: рассылки, аккаунты, подписка, рефералы, помощь
"""
import asyncio
import json
import logging
import os
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile
)
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

import database as db
import keyboards as kb
import sender

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("ADMIN_ID", "0"))
DEFAULT_API_ID   = int(os.getenv("DEFAULT_API_ID", "2040"))
DEFAULT_API_HASH = os.getenv("DEFAULT_API_HASH", "b18441a1ff607e10a989891a5462e627")
REF_PERCENT      = int(os.getenv("REF_PERCENT", "20"))

OWNER_USERNAME   = os.getenv("OWNER_USERNAME", "cryptonaw")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "cryptopuo")
SUB_PRICE        = os.getenv("SUB_PRICE", "89")  # ₽ за период (30 дней)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ══════════════════════════════════════════════════════════════════════════════
#  FSM States
# ══════════════════════════════════════════════════════════════════════════════

class CreateMailing(StatesGroup):
    name     = State()
    account  = State()
    interval = State()
    messages = State()
    chats    = State()
    confirm  = State()


class AddAccount(StatesGroup):
    proxy    = State()
    api_creds = State()
    phone    = State()
    code     = State()
    password = State()


class EnterPromo(StatesGroup):
    code = State()


class AddChat(StatesGroup):
    waiting = State()


class AddMessage(StatesGroup):
    waiting = State()


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

async def check_sub(user_id: int) -> bool:
    return await db.is_subscribed(user_id)


def fmt_time(ts: int) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


STATUS_ICON = {"running": "🟢 Активна", "stopped": "🔴 Остановлена", "paused": "⏸ Пауза"}

# Хранилище сессий Telethon в памяти (пока добавляем аккаунт)
_tg_clients: dict[int, TelegramClient] = {}


# ══════════════════════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    args = msg.text.split()
    ref_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            ref_by = int(args[1][3:])
            if ref_by == msg.from_user.id:
                ref_by = None
        except ValueError:
            pass

    is_new = await db.get_user(msg.from_user.id) is None
    await db.create_user(msg.from_user.id, msg.from_user.username, ref_by)

    # Новым — 3 дня бесплатно
    if is_new:
        await db.add_subscription(msg.from_user.id, 3)

    name = msg.from_user.first_name or msg.from_user.username or "друг"
    gift_line = "🎁 <b>Вам начислено 3 дня бесплатного доступа!</b>\n\n" if is_new else ""
    text = (
        f"👋 Привет, <b>{name}</b>!\n\n"
        "Добро пожаловать в <b>AutoSender</b> — "
        "инструмент для автоматических рассылок через Telegram-аккаунты.\n\n"
        "⚡ <b>Что умеет бот:</b>\n"
        "📨 Рассылка по чатам и группам\n"
        "🤖 Автоответчик в ЛС и группах\n"
        "⏱ Гибкое расписание и интервалы\n"
        "🔗 Управление несколькими аккаунтами\n\n"
        + gift_line
        + "Выберите раздел 👇"
    )
    await msg.answer(text, reply_markup=kb.main_menu_kb(), parse_mode="HTML")



# ══════════════════════════════════════════════════════════════════════════════
#  Главное меню (callback)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыберите раздел 👇",
        reply_markup=kb.main_menu_kb(),
        parse_mode="HTML"
    )
    await cb.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  ПОМОЩЬ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    text = (
        "ℹ️ <b>Справка по боту</b>\n\n"
        "📨 <b>Рассылки</b> — рассылай сообщения по чатам и группам\n"
        "● Текст, фото, пересылка сообщений\n"
        "● Расписание по времени и интервалам\n"
        "● Несколько аккаунтов на одну рассылку\n\n"
        "🔗 <b>Аккаунты</b> — добавляй Telegram-аккаунты\n"
        "● Поддержка прокси SOCKS5\n"
        "● Автоответчик в ЛС и группах\n\n"
        f"💎 <b>Подписка</b> — всего {SUB_PRICE}₽/мес. CryptoBot, TON, карта, промокоды\n"
        "🫂 <b>Рефералы</b> — приглашай друзей и получай % с оплат\n\n"
        "➕ <b>Как добавить аккаунт:</b>\n"
        "1. «Аккаунты» → «Добавить аккаунт»\n"
        "2. При желании укажи прокси SOCKS5\n"
        "3. Введи номер телефона и код из Telegram\n\n"
        "✉️ <b>Как запустить рассылку:</b>\n"
        "1. «Рассылки» → «Создать»\n"
        "2. Выбери аккаунт, добавь сообщения и чаты\n"
        "3. Настрой интервал, расписание → Запуск\n\n"
        f"👑 Владелец: @{OWNER_USERNAME}\n"
        f"🛟 Менеджер (поддержка): @{MANAGER_USERNAME}"
    )
    await cb.message.edit_text(text, reply_markup=kb.help_kb(OWNER_USERNAME, MANAGER_USERNAME), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery):
    text = (
        "🛟 <b>Поддержка</b>\n\n"
        "Если у вас возникли вопросы, проблемы с ботом или предложения — "
        "напишите нам напрямую:\n\n"
        f"👑 Владелец проекта: @{OWNER_USERNAME}\n"
        f"🛟 Менеджер (поддержка): @{MANAGER_USERNAME}\n\n"
        "Отвечаем быстро 🚀"
    )
    await cb.message.edit_text(text, reply_markup=kb.support_kb(OWNER_USERNAME, MANAGER_USERNAME), parse_mode="HTML")
    await cb.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  РАССЫЛКИ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "mailings")
async def cb_mailings(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await check_sub(cb.from_user.id):
        await cb.answer("⚠️ Подписка истекла! Перейдите в раздел «Подписка».", show_alert=True)
        return

    mailings = await db.get_mailings(cb.from_user.id)
    if not mailings:
        text = "📋 <b>Ваши рассылки:</b>\n\nУ вас пока нет рассылок."
    else:
        lines = "\n".join(
            f"● {m['name']} — {STATUS_ICON.get(m['status'], m['status'])}"
            for m in mailings
        )
        text = f"📋 <b>Ваши рассылки:</b>\n\n{lines}\n\nВыберите рассылку или создайте новую:"

    await cb.message.edit_text(text, reply_markup=kb.mailings_kb(mailings), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("mailing:"))
async def cb_mailing_detail(cb: CallbackQuery):
    mailing_id = int(cb.data.split(":")[1])
    m = await db.get_mailing(mailing_id)
    if not m:
        await cb.answer("Рассылка не найдена", show_alert=True)
        return

    accounts = await db.get_accounts(cb.from_user.id)
    acc_phone = "—"
    for a in accounts:
        if a["id"] == m["account_id"]:
            acc_phone = a["phone"]
            break

    chats    = json.loads(m["chats"])
    messages = json.loads(m["messages"])
    status   = STATUS_ICON.get(m["status"], m["status"])

    text = (
        f"📋 <b>{m['name']}</b>\n\n"
        f"📱 Аккаунт: <code>{acc_phone}</code>\n"
        f"⏱ Интервал: {m['interval']} сек\n"
        f"💬 Сообщений: {len(messages)}\n"
        f"📢 Чатов: {len(chats)}\n"
        f"📤 Отправлено: {m['sent_count']}\n"
        f"🔘 Статус: {status}"
    )
    await cb.message.edit_text(text, reply_markup=kb.mailing_detail_kb(mailing_id, m["status"]), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("mailing_start:"))
async def cb_mailing_start(cb: CallbackQuery):
    mailing_id = int(cb.data.split(":")[1])
    ok = await sender.start_mailing(mailing_id)
    if ok:
        await cb.answer("▶️ Рассылка запущена!", show_alert=True)
    else:
        await cb.answer("Рассылка уже запущена", show_alert=True)
    await cb_mailing_detail(cb)


@router.callback_query(F.data.startswith("mailing_stop:"))
async def cb_mailing_stop(cb: CallbackQuery):
    mailing_id = int(cb.data.split(":")[1])
    await sender.stop_mailing(mailing_id)
    await cb.answer("⏹ Рассылка остановлена", show_alert=True)
    await cb_mailing_detail(cb)


@router.callback_query(F.data.startswith("mailing_delete:"))
async def cb_mailing_delete(cb: CallbackQuery):
    mailing_id = int(cb.data.split(":")[1])
    await sender.stop_mailing(mailing_id)
    await db.delete_mailing(mailing_id)
    await cb.answer("🗑 Рассылка удалена", show_alert=True)
    await cb_mailings(cb)


# ── Создание рассылки ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "mailing_create")
async def cb_mailing_create(cb: CallbackQuery, state: FSMContext):
    if not await check_sub(cb.from_user.id):
        await cb.answer("⚠️ Нужна подписка!", show_alert=True)
        return

    await state.set_state(CreateMailing.name)
    await state.update_data(messages=[], chats=[])
    await cb.message.edit_text(
        "➕ <b>Создание рассылки</b>\n\nШаг 1/6: Введите название рассылки:",
        reply_markup=kb.step_back_kb("mailings"),
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(CreateMailing.name)
async def step_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    accounts = await db.get_accounts(msg.from_user.id)
    if not accounts:
        await msg.answer(
            "❗ У вас нет добавленных аккаунтов.\nСначала добавьте аккаунт в разделе «Аккаунты».",
            reply_markup=kb.back_kb("mailings")
        )
        await state.clear()
        return

    await state.set_state(CreateMailing.account)
    await msg.answer(
        "Шаг 2/6: Выберите аккаунт для рассылки:",
        reply_markup=kb.accounts_pick_kb(accounts)
    )


@router.callback_query(F.data.startswith("pick_account:"), CreateMailing.account)
async def step_account(cb: CallbackQuery, state: FSMContext):
    account_id = int(cb.data.split(":")[1])
    await state.update_data(account_id=account_id)
    await state.set_state(CreateMailing.interval)
    await cb.message.edit_text(
        "Шаг 3/6: Введите интервал между сообщениями (в секундах):\n\nНапример: 300 (это 5 минут)",
        reply_markup=kb.step_back_kb("mailing_create")
    )
    await cb.answer()


@router.message(CreateMailing.interval)
async def step_interval(msg: Message, state: FSMContext):
    try:
        interval = int(msg.text.strip())
        if interval < 10:
            await msg.answer("❌ Минимальный интервал — 10 секунд.")
            return
    except ValueError:
        await msg.answer("❌ Введите число (секунды).")
        return

    await state.update_data(interval=interval)
    await state.set_state(CreateMailing.messages)
    data = await state.get_data()
    await msg.answer(
        "Шаг 4/6: Добавьте сообщения для рассылки\n\n"
        "Вы можете добавить текст, фото или фото с подписью.\n"
        "Несколько сообщений — для рандомизации.\n"
        "Минимум 1 сообщение обязательно.",
        reply_markup=kb.messages_kb(data.get("messages", []))
    )


@router.callback_query(F.data == "add_msg_text", CreateMailing.messages)
async def cb_add_msg_text(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddMessage.waiting)
    await cb.message.edit_text(
        "✏️ Отправьте текст или фото для рассылки.\n"
        "Можно отправить несколько фото (до 10) — они будут отправлены альбомом.\n\n"
        "💡 <b>Форматирование</b> (жирный, курсив и т.д.) — выделите текст прямо в Telegram, оно сохранится автоматически.",
        reply_markup=kb.step_back_kb("mailing_create"),
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AddMessage.waiting)
async def receive_message(msg: Message, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages", [])

    if msg.text:
        messages.append({"type": "text", "text": msg.text})
    elif msg.photo:
        messages.append({"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""})
    else:
        await msg.answer("❌ Поддерживаются только текст и фото.")
        return

    await state.update_data(messages=messages)
    await state.set_state(CreateMailing.messages)
    await msg.answer(
        f"✅ Текст добавлен! Всего сообщений: {len(messages)}\n\nДобавьте ещё или нажмите «Готово»:",
        reply_markup=kb.messages_kb(messages)
    )


@router.callback_query(F.data.startswith("del_msg:"), CreateMailing.messages)
async def cb_del_msg(cb: CallbackQuery, state: FSMContext):
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    messages = data.get("messages", [])
    if 0 <= idx < len(messages):
        messages.pop(idx)
    await state.update_data(messages=messages)
    await cb.message.edit_text(
        f"✅ Сообщение удалено. Всего: {len(messages)}\n\nДобавьте ещё или нажмите «Готово»:",
        reply_markup=kb.messages_kb(messages)
    )
    await cb.answer()


@router.callback_query(F.data == "msgs_done", CreateMailing.messages)
async def cb_msgs_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    messages = data.get("messages", [])
    if not messages:
        await cb.answer("❌ Добавьте хотя бы одно сообщение!", show_alert=True)
        return

    await state.set_state(CreateMailing.chats)
    await cb.message.edit_text(
        "Шаг 5/6: Добавьте целевые чаты/группы\n\n"
        "Введите username или ID чата.\nМинимум 1 чат обязателен.",
        reply_markup=kb.chats_kb(data.get("chats", []))
    )
    await cb.answer()


@router.callback_query(F.data == "add_chat", CreateMailing.chats)
async def cb_add_chat(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddChat.waiting)
    await state.update_data(adding_folder=False)
    await cb.message.edit_text(
        "Введите username чата (например @mychat) или числовой ID:",
        reply_markup=kb.step_back_kb("chats_done")
    )
    await cb.answer()


@router.callback_query(F.data == "add_folder", CreateMailing.chats)
async def cb_add_folder(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddChat.waiting)
    await state.update_data(adding_folder=True)
    await cb.message.edit_text(
        "📂 <b>Добавление папки</b>\n\n"
        "Введите username\'ы или ID чатов — каждый с новой строки:\n\n"
        "Пример:\n<code>@chat1\n@chat2\n-100123456789</code>",
        reply_markup=kb.step_back_kb("chats_done"),
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AddChat.waiting)
async def receive_chat(msg: Message, state: FSMContext):
    data = await state.get_data()
    chats = data.get("chats", [])
    adding_folder = data.get("adding_folder", False)

    if adding_folder:
        # Многострочный ввод — каждый чат с новой строки
        new_chats = [line.strip() for line in msg.text.splitlines() if line.strip()]
        chats.extend(new_chats)
        added = len(new_chats)
        label = f"📂 Добавлено {added} чатов из папки!"
    else:
        chats.append(msg.text.strip())
        label = "✅ Чат добавлен!"

    await state.update_data(chats=chats, adding_folder=False)
    await state.set_state(CreateMailing.chats)
    await msg.answer(
        f"{label} Всего: {len(chats)}",
        reply_markup=kb.chats_kb(chats)
    )


@router.callback_query(F.data.startswith("del_chat:"), CreateMailing.chats)
async def cb_del_chat(cb: CallbackQuery, state: FSMContext):
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    chats = data.get("chats", [])
    if 0 <= idx < len(chats):
        chats.pop(idx)
    await state.update_data(chats=chats)
    await cb.message.edit_text(
        f"✅ Чат удалён. Всего: {len(chats)}",
        reply_markup=kb.chats_kb(chats)
    )
    await cb.answer()


@router.callback_query(F.data == "upload_chats", CreateMailing.chats)
async def cb_upload_chats(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Отправьте .txt файл со списком чатов (по одному на строку)", show_alert=True)


@router.message(CreateMailing.chats, F.document)
async def receive_chats_file(msg: Message, state: FSMContext, bot: Bot):
    if not msg.document.file_name.endswith(".txt"):
        await msg.answer("❌ Только .txt файлы")
        return
    file = await bot.get_file(msg.document.file_id)
    content = await bot.download_file(file.file_path)
    lines = content.read().decode("utf-8").splitlines()
    chats = [l.strip() for l in lines if l.strip()]
    data = await state.get_data()
    existing = data.get("chats", [])
    existing.extend(chats)
    await state.update_data(chats=existing)
    await msg.answer(
        f"✅ Загружено {len(chats)} чатов! Всего: {len(existing)}",
        reply_markup=kb.chats_kb(existing)
    )


@router.callback_query(F.data == "chats_done", CreateMailing.chats)
async def cb_chats_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    chats = data.get("chats", [])
    if not chats:
        await cb.answer("❌ Добавьте хотя бы один чат!", show_alert=True)
        return

    await state.set_state(CreateMailing.confirm)
    messages = data.get("messages", [])
    text = (
        "Шаг 6/6: Подтвердите создание рассылки\n\n"
        f"📛 Название: <b>{data.get('name')}</b>\n"
        f"⏱ Интервал: {data.get('interval')} сек\n"
        f"💬 Сообщений: {len(messages)}\n"
        f"📢 Чатов: {len(chats)}\n\n"
        "Готово к запуску?"
    )
    await cb.message.edit_text(text, reply_markup=kb.confirm_mailing_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.in_({"mailing_run_now", "mailing_save_only"}), CreateMailing.confirm)
async def cb_confirm_mailing(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mailing_id = await db.create_mailing(
        user_id    = cb.from_user.id,
        name       = data["name"],
        account_id = data["account_id"],
        interval   = data["interval"],
        messages   = json.dumps(data["messages"]),
        chats      = json.dumps(data["chats"]),
    )

    if cb.data == "mailing_run_now":
        await sender.start_mailing(mailing_id)
        text = "🚀 Рассылка создана и запущена!"
    else:
        text = "💾 Рассылка сохранена (не запущена)."

    await state.clear()
    await cb.message.edit_text(text, reply_markup=kb.back_kb("mailings"))
    await cb.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  АККАУНТЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "accounts")
async def cb_accounts(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    accounts = await db.get_accounts(cb.from_user.id)
    limit = 3  # лимит аккаунтов на подписку (можно менять)
    text = (
        f"🔗 <b>Аккаунты</b>\n\n"
        f"📊 Добавлено: {len(accounts)} из {limit}\nДоступно слотов: {max(0, limit - len(accounts))}"
    )
    await cb.message.edit_text(text, reply_markup=kb.accounts_kb(accounts), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("account:"))
async def cb_account_detail(cb: CallbackQuery):
    account_id = int(cb.data.split(":")[1])
    acc = await db.get_account(account_id)
    if not acc:
        await cb.answer("Аккаунт не найден", show_alert=True)
        return

    status = "🟢 Активен" if acc["status"] == "active" else "🔴 Неактивен"
    proxy  = acc["proxy"] or "Нет"
    text = (
        f"📱 <b>{acc['phone']}</b>\n\n"
        f"🔘 Статус: {status}\n"
        f"🌐 Прокси: <code>{proxy}</code>\n"
        f"🔑 API: {'Свой' if acc['api_id'] else 'Стандартный'}"
    )
    await cb.message.edit_text(text, reply_markup=kb.account_detail_kb(account_id), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("account_delete:"))
async def cb_account_delete(cb: CallbackQuery):
    account_id = int(cb.data.split(":")[1])
    await db.delete_account(account_id)
    await cb.answer("🗑 Аккаунт удалён", show_alert=True)
    await cb_accounts(cb)


# ── Добавление аккаунта ───────────────────────────────────────────────────────

@router.callback_query(F.data == "account_add")
async def cb_account_add(cb: CallbackQuery, state: FSMContext):
    if not await check_sub(cb.from_user.id):
        await cb.answer("⚠️ Нужна подписка!", show_alert=True)
        return

    accounts = await db.get_accounts(cb.from_user.id)
    limit = 3
    if len(accounts) >= limit:
        await cb.answer(f"❌ Лимит {limit} аккаунтов достигнут. Купите расширенный план.", show_alert=True)
        return

    await state.set_state(AddAccount.proxy)
    await state.update_data(proxy=None, api_id=None, api_hash=None)

    text = (
        f"➕ <b>Добавление аккаунта</b>\n\n"
        f"📊 У вас {len(accounts)}/{limit} аккаунтов\nОсталось: {limit - len(accounts)}\n\n"
        "<b>Шаг 1 из 3</b>\n\nХотите использовать прокси SOCKS5?\n\n"
        "Если да — введите в формате:\n"
        "<code>socks5://host:port</code>\nили\n<code>socks5://user:pass@host:port</code>"
    )
    await cb.message.edit_text(text, reply_markup=kb.proxy_choice_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "proxy_no", AddAccount.proxy)
async def cb_proxy_no(cb: CallbackQuery, state: FSMContext):
    await _show_api_step(cb, state)


@router.callback_query(F.data == "proxy_yes", AddAccount.proxy)
async def cb_proxy_yes(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "Введите прокси в формате:\n<code>socks5://host:port</code>",
        reply_markup=kb.step_back_kb("account_add"),
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AddAccount.proxy)
async def receive_proxy(msg: Message, state: FSMContext):
    proxy = msg.text.strip()
    if not proxy.startswith("socks5://"):
        await msg.answer("❌ Неверный формат. Используйте socks5://host:port")
        return
    await state.update_data(proxy=proxy)
    await _show_api_step_msg(msg, state)


async def _show_api_step(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddAccount.api_creds)
    await cb.message.edit_text(
        "➕ <b>Добавление аккаунта</b>\n\n<b>Шаг 2 из 3</b>\n\n"
        "Хотите использовать собственный API ID и Hash?\n\n"
        "Получить: https://my.telegram.org\n\n"
        "Если нет — используются стандартные настройки.",
        reply_markup=kb.api_choice_kb(),
        parse_mode="HTML"
    )
    await cb.answer()


async def _show_api_step_msg(msg: Message, state: FSMContext):
    await state.set_state(AddAccount.api_creds)
    await msg.answer(
        "➕ <b>Добавление аккаунта</b>\n\n<b>Шаг 2 из 3</b>\n\n"
        "Хотите использовать собственный API ID и Hash?\n\n"
        "Получить: https://my.telegram.org\n\n"
        "Если нет — используются стандартные настройки.",
        reply_markup=kb.api_choice_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "api_no", AddAccount.api_creds)
async def cb_api_no(cb: CallbackQuery, state: FSMContext):
    await _show_phone_step(cb, state)


@router.callback_query(F.data == "api_yes", AddAccount.api_creds)
async def cb_api_yes(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "Введите API_ID и API_HASH через пробел:\n"
        "Например: <code>12345678 abcdef1234567890abcdef1234567890</code>",
        reply_markup=kb.step_back_kb("account_add"),
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AddAccount.api_creds)
async def receive_api(msg: Message, state: FSMContext):
    parts = msg.text.strip().split()
    if len(parts) != 2:
        await msg.answer("❌ Введите API_ID и API_HASH через пробел")
        return
    try:
        api_id = int(parts[0])
    except ValueError:
        await msg.answer("❌ API_ID должен быть числом")
        return
    await state.update_data(api_id=api_id, api_hash=parts[1])
    await _show_phone_step_msg(msg, state)


async def _show_phone_step(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddAccount.phone)
    await cb.message.edit_text(
        "➕ <b>Добавление аккаунта</b>\n\n<b>Шаг 3 из 3</b>\n\n"
        "Введите номер телефона в международном формате:\nНапример: <code>+380991234567</code>",
        reply_markup=kb.step_back_kb("account_add"),
        parse_mode="HTML"
    )
    await cb.answer()


async def _show_phone_step_msg(msg: Message, state: FSMContext):
    await state.set_state(AddAccount.phone)
    await msg.answer(
        "➕ <b>Добавление аккаунта</b>\n\n<b>Шаг 3 из 3</b>\n\n"
        "Введите номер телефона в международном формате:\nНапример: <code>+380991234567</code>",
        reply_markup=kb.step_back_kb("account_add"),
        parse_mode="HTML"
    )


@router.message(AddAccount.phone)
async def receive_phone(msg: Message, state: FSMContext, bot: Bot):
    phone = msg.text.strip().replace(" ", "")
    if not phone.startswith("+"):
        await msg.answer("❌ Номер должен начинаться с +.\nПопробуйте снова:")
        return

    data  = await state.get_data()
    api_id   = data.get("api_id")   or DEFAULT_API_ID
    api_hash = data.get("api_hash") or DEFAULT_API_HASH
    proxy_str = data.get("proxy")

    proxy = None
    if proxy_str:
        import re
        m = re.match(r"socks5://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)", proxy_str)
        if m:
            user, pwd, host, port = m.groups()
            proxy = (2, host, int(port), True, user, pwd) if user else (2, host, int(port))

    client = TelegramClient(StringSession(), api_id, api_hash, proxy=proxy)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
        _tg_clients[msg.from_user.id] = client
        await state.update_data(
            phone=phone, phone_code_hash=sent.phone_code_hash,
            api_id=api_id, api_hash=api_hash
        )
        await state.set_state(AddAccount.code)
        await msg.answer(
            "📱 <b>Код отправлен!</b>\n\n"
            "📲 Проверьте приложение Telegram на других ваших устройствах или Telegram Web — код придёт туда.\n\n"
            "1️⃣2️⃣3️⃣4️⃣ Введите код с помощью кнопок:\n\nКод: ■ ■ ■ ■ ■",
            reply_markup=kb.numpad_kb(""),
            parse_mode="HTML"
        )
    except Exception as e:
        await client.disconnect()
        log.error(f"send_code error: {e}")
        await msg.answer(f"❌ Ошибка: {e}\n\nПопробуйте снова:")


@router.callback_query(F.data.startswith("code:"), AddAccount.code)
async def cb_code(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    current = data.get("code_input", "")
    action  = cb.data.split(":")[1]

    if action == "del":
        current = current[:-1]
    elif action == "back":
        current = current[:-1]
    elif action == "confirm":
        if len(current) < 5:
            await cb.answer("❌ Введите все 5 цифр", show_alert=True)
            return
        await _do_confirm_code(cb, state, current)
        return
    elif action == "noop":
        await cb.answer()
        return
    else:
        if len(current) < 5:
            current += action

    await state.update_data(code_input=current)
    display = " ".join(list(current.ljust(5, "■")[:5]))
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.numpad_kb(current))
    except Exception:
        pass
    await cb.answer()


async def _do_confirm_code(cb: CallbackQuery, state: FSMContext, code: str):
    data     = await state.get_data()
    client   = _tg_clients.get(cb.from_user.id)
    if not client:
        await cb.answer("❌ Сессия потеряна, начните заново", show_alert=True)
        return

    try:
        await client.sign_in(
            phone=data["phone"],
            code=code,
            phone_code_hash=data["phone_code_hash"]
        )
        session_str = client.session.save()
        await client.disconnect()
        _tg_clients.pop(cb.from_user.id, None)

        account_id = await db.create_account(
            user_id  = cb.from_user.id,
            phone    = data["phone"],
            proxy    = data.get("proxy"),
            api_id   = data.get("api_id"),
            api_hash = data.get("api_hash"),
        )
        await db.save_session(account_id, session_str)
        await state.clear()

        await cb.message.edit_text(
            f"✅ Аккаунт <code>{data['phone']}</code> успешно добавлен!",
            reply_markup=kb.back_kb("accounts"),
            parse_mode="HTML"
        )
        await cb.answer()

    except SessionPasswordNeededError:
        await state.set_state(AddAccount.password)
        await cb.message.edit_text(
            "🔐 У аккаунта включена двухфакторная аутентификация.\n\nВведите пароль:",
            reply_markup=kb.step_back_kb("accounts")
        )
        await cb.answer()

    except PhoneCodeInvalidError:
        await cb.answer("❌ Неверный код! Попробуйте снова.", show_alert=True)
        await state.update_data(code_input="")
        await cb.message.edit_reply_markup(reply_markup=kb.numpad_kb(""))

    except Exception as e:
        log.error(f"sign_in error: {e}")
        await cb.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.message(AddAccount.password)
async def receive_password(msg: Message, state: FSMContext):
    data   = await state.get_data()
    client = _tg_clients.get(msg.from_user.id)
    if not client:
        await msg.answer("❌ Сессия потеряна, начните заново")
        await state.clear()
        return

    try:
        await client.sign_in(password=msg.text.strip())
        session_str = client.session.save()
        await client.disconnect()
        _tg_clients.pop(msg.from_user.id, None)

        account_id = await db.create_account(
            user_id  = msg.from_user.id,
            phone    = data["phone"],
            proxy    = data.get("proxy"),
            api_id   = data.get("api_id"),
            api_hash = data.get("api_hash"),
        )
        await db.save_session(account_id, session_str)
        await state.clear()
        await msg.answer(
            f"✅ Аккаунт <code>{data['phone']}</code> успешно добавлен!",
            reply_markup=kb.back_kb("accounts"),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.answer(f"❌ Неверный пароль: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ПОДПИСКА
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "subscription")
async def cb_subscription(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    user    = await db.get_user(cb.from_user.id)
    subbed  = await check_sub(cb.from_user.id)
    sub_until = fmt_time(user["sub_until"]) if user and user["sub_until"] > 0 else "—"

    status = f"✅ Активна до {sub_until}" if subbed else "❌ Нет активной подписки"
    text = (
        f"💳 <b>Подписка</b>\n\n"
        f"🔘 Статус: {status}\n\n"
        "Выберите действие:"
    )
    await cb.message.edit_text(text, reply_markup=kb.subscription_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "enter_promo")
async def cb_enter_promo(cb: CallbackQuery, state: FSMContext):
    await state.set_state(EnterPromo.code)
    await cb.message.edit_text(
        "🎟 Введите промокод:",
        reply_markup=kb.step_back_kb("subscription")
    )
    await cb.answer()


@router.message(EnterPromo.code)
async def receive_promo(msg: Message, state: FSMContext):
    code = msg.text.strip().lower()
    days = await db.use_promo(code)
    if days == 0:
        await msg.answer("❌ Промокод недействителен или уже использован.", reply_markup=kb.back_kb("subscription"))
        await state.clear()
        return

    until = await db.add_subscription(msg.from_user.id, days)
    await state.clear()
    await msg.answer(
        f"✅ Промокод активирован!\n\n"
        f"Подписка продлена на <b>{days} дней</b>.\n"
        f"Активна до: <b>{fmt_time(until)}</b>",
        reply_markup=kb.back_kb("main_menu"),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "buy_sub")
async def cb_buy_sub(cb: CallbackQuery):
    text = (
        "💳 <b>Купить подписку</b>\n\n"
        f"🔥 Всего <b>{SUB_PRICE}₽</b> за 30 дней безлимитного доступа!\n\n"
        "В подписку входит:\n"
        "📨 Безлимит рассылок\n"
        "🔗 До 3 аккаунтов\n"
        "⏱ Гибкое расписание\n"
        "🤖 Автоответчик\n\n"
        "💰 Оплата: CryptoBot, TON, карта\n\n"
        f"Для оплаты напишите менеджеру: @{MANAGER_USERNAME}"
    )
    await cb.message.edit_text(text, reply_markup=kb.buy_sub_kb(MANAGER_USERNAME), parse_mode="HTML")
    await cb.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  РЕФЕРАЛЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "referrals")
async def cb_referrals(cb: CallbackQuery):
    refs = await db.get_referrals(cb.from_user.id)
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref{cb.from_user.id}"

    if refs:
        lines = "\n".join(
            f"● @{r['username'] or r['ref_user']}" for r in refs
        )
        ref_text = f"Ваши рефералы ({len(refs)}):\n{lines}"
    else:
        ref_text = "У вас пока нет рефералов."

    text = (
        f"🤝 <b>Рефералы</b>\n\n"
        f"Приглашайте друзей и получайте <b>{REF_PERCENT}%</b> с каждой их оплаты!\n\n"
        f"🔗 Ваша реферальная ссылка:\n<code>{link}</code>\n\n"
        f"{ref_text}"
    )
    await cb.message.edit_text(text, reply_markup=kb.back_kb("main_menu"), parse_mode="HTML")
    await cb.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  ДМ рассылка (заглушка)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "dm_mailing")
async def cb_dm_mailing(cb: CallbackQuery):
    await cb.answer("Функция рассылки в ЛС доступна в @feAutoSenderDMbot", show_alert=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN команды
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer(
        "🛠 <b>Админ-панель</b>\n\n"
        "/givesub @username &lt;days&gt; — выдать подписку по юзернейму\n"
        "/givesub ID &lt;days&gt; — выдать подписку по user_id\n"
        "/addpromo &lt;code&gt; &lt;days&gt; — создать промокод\n"
        "/stats — статистика",
        parse_mode="HTML"
    )


@router.message(Command("givesub"))
async def cmd_givesub(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return

    args = msg.text.split()
    if len(args) != 3:
        await msg.answer(
            "❌ Использование:\n"
            "<code>/givesub @username 30</code>\n"
            "<code>/givesub 123456789 30</code>",
            parse_mode="HTML"
        )
        return

    target_raw = args[1].lstrip("@")
    try:
        days = int(args[2])
        if days <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Дней должно быть положительным числом.")
        return

    # Ищем юзера — по ID или по username
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Попробуем как числовой ID
        try:
            user_id = int(target_raw)
            async with conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
                user = await cur.fetchone()
        except ValueError:
            user_id = None
            user = None

        # Если не нашли по ID — ищем по username
        if not user:
            async with conn.execute(
                "SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (target_raw,)
            ) as cur:
                user = await cur.fetchone()

    if not user:
        await msg.answer(
            f"❌ Пользователь <code>{args[1]}</code> не найден в базе.\n\n"
            "Пользователь должен сначала написать боту /start.",
            parse_mode="HTML"
        )
        return

    until = await db.add_subscription(user["user_id"], days)
    display = f"@{user['username']}" if user["username"] else f"ID {user['user_id']}"

    await msg.answer(
        f"✅ Подписка выдана!\n\n"
        f"👤 Пользователь: <b>{display}</b>\n"
        f"📅 Дней добавлено: <b>{days}</b>\n"
        f"⏳ Активна до: <b>{fmt_time(until)}</b>",
        parse_mode="HTML"
    )

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user["user_id"],
            f"🎉 <b>Вам выдана подписка!</b>\n\n"
            f"📅 Добавлено дней: <b>{days}</b>\n"
            f"⏳ Активна до: <b>{fmt_time(until)}</b>",
            parse_mode="HTML"
        )
    except Exception:
        await msg.answer("⚠️ Не удалось уведомить пользователя (возможно, заблокировал бота).")


@router.message(Command("addpromo"))
async def cmd_addpromo(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    args = msg.text.split()
    if len(args) != 3:
        await msg.answer("Использование: /addpromo <code> <days>")
        return
    code, days = args[1], int(args[2])
    async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO promo_codes (code, days, uses_left) VALUES (?,?,9999)",
            (code.lower(), days)
        )
        await conn.commit()
    await msg.answer(f"✅ Промокод <code>{code}</code> на {days} дней создан.", parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM accounts") as cur:
            accounts = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM mailings") as cur:
            mailings = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM mailings WHERE status='running'") as cur:
            running = (await cur.fetchone())[0]

    await msg.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👤 Пользователей: {users}\n"
        f"📱 Аккаунтов: {accounts}\n"
        f"📋 Рассылок: {mailings}\n"
        f"▶️ Активных: {running}",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  БЫСТРЫЕ КОМАНДЫ (алиасы)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("help"))
async def cmd_help(msg: Message, state: FSMContext):
    await state.clear()
    text = (
        "ℹ️ <b>Справка по боту</b>\n\n"
        "📨 <b>Рассылки</b> — рассылай сообщения по чатам и группам\n"
        "● Текст, фото, пересылка сообщений\n"
        "● Расписание по времени и интервалам\n"
        "● Несколько аккаунтов на одну рассылку\n\n"
        "🔗 <b>Аккаунты</b> — добавляй Telegram-аккаунты\n"
        "● Поддержка прокси SOCKS5\n"
        "● Автоответчик в ЛС и группах\n\n"
        f"💎 <b>Подписка</b> — всего {SUB_PRICE}₽/мес. CryptoBot, TON, карта, промокоды\n"
        "🫂 <b>Рефералы</b> — приглашай друзей и получай % с оплат\n\n"
        f"👑 Владелец: @{OWNER_USERNAME}\n"
        f"🛟 Менеджер (поддержка): @{MANAGER_USERNAME}\n\n"
        "📋 <b>Команды:</b>\n"
        "/menu — главное меню\n"
        "/mymailings — мои рассылки\n"
        "/accounts — мои аккаунты\n"
        "/mysubs — моя подписка\n"
        "/buy — купить подписку\n"
        "/referrals — рефералы\n"
        "/support — поддержка"
    )
    await msg.answer(text, reply_markup=kb.help_kb(OWNER_USERNAME, MANAGER_USERNAME), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "🏠 <b>Главное меню</b>\n\nВыберите раздел 👇",
        reply_markup=kb.main_menu_kb(),
        parse_mode="HTML"
    )


@router.message(Command("mysubs", "subscription", "sub"))
async def cmd_mysubs(msg: Message, state: FSMContext):
    await state.clear()
    user      = await db.get_user(msg.from_user.id)
    subbed    = await check_sub(msg.from_user.id)
    sub_until = fmt_time(user["sub_until"]) if user and user["sub_until"] > 0 else "—"
    status    = f"✅ Активна до {sub_until}" if subbed else "❌ Нет активной подписки"

    text = (
        f"💎 <b>Подписка</b>\n\n"
        f"🔘 Статус: {status}\n\n"
        "Выберите действие:"
    )
    await msg.answer(text, reply_markup=kb.subscription_kb(), parse_mode="HTML")


@router.message(Command("mymailings", "mailings"))
async def cmd_mymailings(msg: Message, state: FSMContext):
    await state.clear()
    if not await check_sub(msg.from_user.id):
        await msg.answer("⚠️ Подписка истекла! Перейдите в раздел «Подписка».", reply_markup=kb.subscription_kb())
        return

    mailings = await db.get_mailings(msg.from_user.id)
    if not mailings:
        text = "📨 <b>Ваши рассылки:</b>\n\nУ вас пока нет рассылок."
    else:
        lines = "\n".join(
            f"● {m['name']} — {STATUS_ICON.get(m['status'], m['status'])}"
            for m in mailings
        )
        text = f"📨 <b>Ваши рассылки:</b>\n\n{lines}\n\nВыберите рассылку или создайте новую:"

    await msg.answer(text, reply_markup=kb.mailings_kb(mailings), parse_mode="HTML")


@router.message(Command("buy"))
async def cmd_buy(msg: Message, state: FSMContext):
    await state.clear()
    text = (
        "💳 <b>Купить подписку</b>\n\n"
        f"🔥 Всего <b>{SUB_PRICE}₽</b> за 30 дней безлимитного доступа!\n\n"
        "В подписку входит:\n"
        "📨 Безлимит рассылок\n"
        "🔗 До 3 аккаунтов\n"
        "⏱ Гибкое расписание\n"
        "🤖 Автоответчик\n\n"
        "💰 Оплата: CryptoBot, TON, карта\n\n"
        f"Для оплаты напишите менеджеру: @{MANAGER_USERNAME}"
    )
    await msg.answer(text, reply_markup=kb.buy_sub_kb(MANAGER_USERNAME), parse_mode="HTML")


@router.message(Command("support"))
async def cmd_support(msg: Message, state: FSMContext):
    await state.clear()
    text = (
        "🛟 <b>Поддержка</b>\n\n"
        "Если у вас возникли вопросы, проблемы с ботом или предложения — "
        "напишите нам напрямую:\n\n"
        f"👑 Владелец проекта: @{OWNER_USERNAME}\n"
        f"🛟 Менеджер (поддержка): @{MANAGER_USERNAME}\n\n"
        "Отвечаем быстро 🚀"
    )
    await msg.answer(text, reply_markup=kb.support_kb(OWNER_USERNAME, MANAGER_USERNAME), parse_mode="HTML")


@router.message(Command("accounts"))
async def cmd_accounts(msg: Message, state: FSMContext):
    await state.clear()
    accounts = await db.get_accounts(msg.from_user.id)
    limit = 3
    text = (
        f"🔗 <b>Аккаунты</b>\n\n"
        f"📊 Добавлено: {len(accounts)} из {limit}\nДоступно слотов: {max(0, limit - len(accounts))}"
    )
    await msg.answer(text, reply_markup=kb.accounts_kb(accounts), parse_mode="HTML")


@router.message(Command("referrals", "ref"))
async def cmd_referrals(msg: Message, state: FSMContext):
    await state.clear()
    refs = await db.get_referrals(msg.from_user.id)
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref{msg.from_user.id}"

    if refs:
        lines = "\n".join(f"● @{r['username'] or r['ref_user']}" for r in refs)
        ref_text = f"Ваши рефералы ({len(refs)}):\n{lines}"
    else:
        ref_text = "У вас пока нет рефералов."

    text = (
        f"🫂 <b>Рефералы</b>\n\n"
        f"Приглашайте друзей и получайте <b>{REF_PERCENT}%</b> с каждой их оплаты!\n\n"
        f"🔗 Ваша реферальная ссылка:\n<code>{link}</code>\n\n"
        f"{ref_text}"
    )
    await msg.answer(text, reply_markup=kb.back_kb("main_menu"), parse_mode="HTML")


async def setup_bot_commands():
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start",       description="🚀 Запустить бота"),
        BotCommand(command="menu",        description="🏠 Главное меню"),
        BotCommand(command="mymailings",  description="📨 Мои рассылки"),
        BotCommand(command="accounts",    description="🔗 Мои аккаунты"),
        BotCommand(command="mysubs",      description="💎 Моя подписка"),
        BotCommand(command="buy",         description="💳 Купить / продлить подписку"),
        BotCommand(command="referrals",   description="🫂 Реферальная программа"),
        BotCommand(command="support",     description="🛟 Поддержка"),
        BotCommand(command="help",        description="ℹ️ Помощь"),
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    await db.init_db()
    await sender.restore_mailings()
    await setup_bot_commands()
    log.info("Bot started")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())

