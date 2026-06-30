from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── ГЛАВНОЕ МЕНЮ ──────────────────────────────────────────────────────────────

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📨 Мои рассылки", callback_data="mailings"),
            InlineKeyboardButton(text="🔗 Аккаунты",     callback_data="accounts"),
        ],
        [
            InlineKeyboardButton(text="💎 Подписка",     callback_data="subscription"),
            InlineKeyboardButton(text="🫂 Рефералы",     callback_data="referrals"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Помощь",       callback_data="help"),
            InlineKeyboardButton(text="🛟 Поддержка",    callback_data="support"),
        ],
    ])


# ── РАССЫЛКИ ──────────────────────────────────────────────────────────────────

def mailings_kb(mailings):
    buttons = []
    for m in mailings:
        icon = "🟢" if m["status"] == "running" else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {m['name']}",
            callback_data=f"mailing:{m['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="✨ Создать рассылку", callback_data="mailing_create")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню",     callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mailing_detail_kb(mailing_id: int, status: str):
    toggle = ("⏸ Остановить", f"mailing_stop:{mailing_id}") if status == "running" else \
             ("▶️ Запустить",  f"mailing_start:{mailing_id}")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle[0],              callback_data=toggle[1])],
        [InlineKeyboardButton(text="🗑 Удалить",           callback_data=f"mailing_delete:{mailing_id}")],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="mailings")],
    ])


def back_kb(cb: str = "main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=cb)]
    ])


def step_back_kb(cb: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=cb)]
    ])


def accounts_pick_kb(accounts, back_cb: str = "mailing_create"):
    buttons = []
    for a in accounts:
        buttons.append([InlineKeyboardButton(
            text=f"📱 {a['phone']}",
            callback_data=f"pick_account:{a['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def messages_kb(messages: list):
    buttons = []
    for i, msg in enumerate(messages):
        preview = msg.get("text", "")[:22] or "[фото]"
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {preview}",
            callback_data=f"del_msg:{i}"
        )])
    buttons.append([
        InlineKeyboardButton(text="✏️ Текст / фото", callback_data="add_msg_text"),
        InlineKeyboardButton(text="📩 Переслать",     callback_data="add_msg_forward"),
    ])
    if messages:
        buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="msgs_done")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mailing_step3")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def chats_kb(chats: list):
    buttons = []
    for i, chat in enumerate(chats):
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {chat}",
            callback_data=f"del_chat:{i}"
        )])
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить чат",   callback_data="add_chat"),
        InlineKeyboardButton(text="📂 Добавить папку", callback_data="add_folder"),
    ])
    buttons.append([InlineKeyboardButton(text="📋 Загрузить .txt", callback_data="upload_chats")])
    if chats:
        buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="chats_done")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mailing_step4")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_mailing_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить сейчас",          callback_data="mailing_run_now")],
        [InlineKeyboardButton(text="💾 Сохранить без запуска",     callback_data="mailing_save_only")],
        [InlineKeyboardButton(text="◀️ Назад",                     callback_data="mailing_step5")],
    ])


# ── АККАУНТЫ ──────────────────────────────────────────────────────────────────

def accounts_kb(accounts):
    buttons = []
    for a in accounts:
        icon = "🟢" if a["status"] == "active" else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {a['phone']}",
            callback_data=f"account:{a['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="account_add")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню",     callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def account_detail_kb(account_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data=f"account_delete:{account_id}")],
        [InlineKeyboardButton(text="◀️ Назад",           callback_data="accounts")],
    ])


def proxy_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, добавить прокси", callback_data="proxy_yes"),
            InlineKeyboardButton(text="⏩ Пропустить",          callback_data="proxy_no"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="accounts")],
    ])


def api_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, ввести API", callback_data="api_yes"),
            InlineKeyboardButton(text="⏩ Пропустить",     callback_data="api_no"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="account_add")],
    ])


def numpad_kb(current_code: str = ""):
    filled  = list(current_code)
    display = ""
    for i in range(5):
        display += (filled[i] if i < len(filled) else "·") + " "
    display = display.strip()

    buttons = [
        [InlineKeyboardButton(text=f"🔢  {display}", callback_data="noop")],
        [
            InlineKeyboardButton(text="1", callback_data="code:1"),
            InlineKeyboardButton(text="2", callback_data="code:2"),
            InlineKeyboardButton(text="3", callback_data="code:3"),
        ],
        [
            InlineKeyboardButton(text="4", callback_data="code:4"),
            InlineKeyboardButton(text="5", callback_data="code:5"),
            InlineKeyboardButton(text="6", callback_data="code:6"),
        ],
        [
            InlineKeyboardButton(text="7", callback_data="code:7"),
            InlineKeyboardButton(text="8", callback_data="code:8"),
            InlineKeyboardButton(text="9", callback_data="code:9"),
        ],
        [
            InlineKeyboardButton(text="⌫",  callback_data="code:del"),
            InlineKeyboardButton(text="0",  callback_data="code:0"),
            InlineKeyboardButton(text="◀️", callback_data="code:back"),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад",       callback_data="account_phone"),
            InlineKeyboardButton(text="✅ Подтвердить",  callback_data="code:confirm"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── ПОДПИСКА ──────────────────────────────────────────────────────────────────

def subscription_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Ввести промокод",  callback_data="enter_promo")],
        [InlineKeyboardButton(text="💳 Купить подписку",  callback_data="buy_sub")],
        [InlineKeyboardButton(text="🏠 Главное меню",     callback_data="main_menu")],
    ])


# ── ПОМОЩЬ ────────────────────────────────────────────────────────────────────

def help_kb(owner: str = "cryptonaw", manager: str = "cryptopuo"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Политика конфиденциальности", url="https://t.me/")],
        [InlineKeyboardButton(text="📄 Пользовательское соглашение", url="https://t.me/")],
        [
            InlineKeyboardButton(text="👑 Владелец",  url=f"https://t.me/{owner}"),
            InlineKeyboardButton(text="🛟 Менеджер",  url=f"https://t.me/{manager}"),
        ],
        [InlineKeyboardButton(text="📩 Рассылка в ЛС", callback_data="dm_mailing")],
        [InlineKeyboardButton(text="🏠 Главное меню",  callback_data="main_menu")],
    ])


def support_kb(owner: str = "cryptonaw", manager: str = "cryptopuo"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Владелец",  url=f"https://t.me/{owner}")],
        [InlineKeyboardButton(text="🛟 Менеджер (поддержка)", url=f"https://t.me/{manager}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def buy_sub_kb(manager: str = "cryptopuo"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Написать менеджеру", url=f"https://t.me/{manager}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="subscription")],
    ])
