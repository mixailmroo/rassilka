"""
Фоновый воркер для рассылок через Telethon.
Каждая активная рассылка работает в своей asyncio задаче.
"""
import asyncio
import json
import logging
import os
import time

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, UserBannedInChannelError,
    ChatWriteForbiddenError, PeerFloodError,
)

import database as db

log = logging.getLogger(__name__)

DEFAULT_API_ID   = int(os.getenv("DEFAULT_API_ID",   "2040"))
DEFAULT_API_HASH = os.getenv("DEFAULT_API_HASH", "b18441a1ff607e10a989891a5462e627")

# mailing_id -> asyncio.Task
_running: dict[int, asyncio.Task] = {}


async def _run_mailing(mailing_id: int):
    mailing = await db.get_mailing(mailing_id)
    if not mailing:
        return

    account = await db.get_account(mailing["account_id"])
    if not account or not account["session"]:
        log.warning(f"Mailing {mailing_id}: no session")
        return

    chats    = json.loads(mailing["chats"])
    messages = json.loads(mailing["messages"])
    interval = mailing["interval"]

    api_id   = account["api_id"]   or DEFAULT_API_ID
    api_hash = account["api_hash"] or DEFAULT_API_HASH

    proxy = None
    if account["proxy"]:
        proxy = _parse_proxy(account["proxy"])

    client = TelegramClient(
        StringSession(account["session"]),
        api_id, api_hash,
        proxy=proxy,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            log.warning(f"Mailing {mailing_id}: not authorized")
            return

        msg_index = 0
        while True:
            mailing = await db.get_mailing(mailing_id)
            if not mailing or mailing["status"] != "running":
                break

            msg = messages[msg_index % len(messages)]
            for chat in chats:
                try:
                    if msg.get("type") == "text":
                        await client.send_message(chat, msg["text"])
                    elif msg.get("type") == "photo":
                        await client.send_file(chat, msg["file_id"], caption=msg.get("caption", ""))
                    await db.increment_sent(mailing_id)
                    await asyncio.sleep(1)
                except (UserBannedInChannelError, ChatWriteForbiddenError) as e:
                    log.warning(f"Mailing {mailing_id} chat {chat}: {e}")
                except FloodWaitError as e:
                    log.warning(f"FloodWait {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                except PeerFloodError:
                    log.warning(f"PeerFlood on mailing {mailing_id}")
                    await asyncio.sleep(300)
                except Exception as e:
                    log.error(f"Mailing {mailing_id} error: {e}")

            msg_index += 1
            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        pass
    finally:
        await client.disconnect()
        await db.update_mailing_status(mailing_id, "stopped")
        _running.pop(mailing_id, None)


def _parse_proxy(proxy_str: str):
    """socks5://host:port or socks5://user:pass@host:port"""
    import re
    m = re.match(r"socks5://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)", proxy_str)
    if m:
        user, pwd, host, port = m.groups()
        if user:
            return (2, host, int(port), True, user, pwd)
        return (2, host, int(port))
    return None


async def start_mailing(mailing_id: int):
    if mailing_id in _running:
        return False
    await db.update_mailing_status(mailing_id, "running")
    task = asyncio.create_task(_run_mailing(mailing_id))
    _running[mailing_id] = task
    return True


async def stop_mailing(mailing_id: int):
    task = _running.get(mailing_id)
    if task:
        task.cancel()
        _running.pop(mailing_id, None)
    await db.update_mailing_status(mailing_id, "stopped")


async def restore_mailings():
    """Восстановить running рассылки после перезапуска бота"""
    async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
        conn.row_factory = __import__("aiosqlite").Row
        async with conn.execute("SELECT id FROM mailings WHERE status='running'") as cur:
            rows = await cur.fetchall()
    for row in rows:
        await start_mailing(row["id"])
