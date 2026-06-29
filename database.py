import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                ref_by      INTEGER,
                sub_until   INTEGER DEFAULT 0,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                phone       TEXT NOT NULL,
                session     TEXT,
                api_id      INTEGER,
                api_hash    TEXT,
                proxy       TEXT,
                status      TEXT DEFAULT 'active',
                created_at  INTEGER DEFAULT (strftime('%s','now')),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS mailings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT NOT NULL,
                account_id  INTEGER,
                interval    INTEGER DEFAULT 300,
                messages    TEXT DEFAULT '[]',
                chats       TEXT DEFAULT '[]',
                status      TEXT DEFAULT 'stopped',
                sent_count  INTEGER DEFAULT 0,
                created_at  INTEGER DEFAULT (strftime('%s','now')),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_by      INTEGER NOT NULL,
                ref_user    INTEGER NOT NULL,
                paid        INTEGER DEFAULT 0,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                code        TEXT PRIMARY KEY,
                days        INTEGER DEFAULT 0,
                uses_left   INTEGER DEFAULT 1,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            INSERT OR IGNORE INTO promo_codes (code, days, uses_left) VALUES ('free', 7, 9999);
        """)
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()


async def create_user(user_id: int, username: str = None, ref_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, ref_by) VALUES (?,?,?)",
            (user_id, username, ref_by)
        )
        await db.commit()
        if ref_by:
            await db.execute(
                "INSERT OR IGNORE INTO referrals (ref_by, ref_user) VALUES (?,?)",
                (ref_by, user_id)
            )
            await db.commit()


async def is_subscribed(user_id: int) -> bool:
    import time
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT sub_until FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            return row[0] > time.time()


async def add_subscription(user_id: int, days: int):
    import time
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT sub_until FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        now = time.time()
        current = row[0] if row and row[0] > now else now
        new_until = int(current + days * 86400)
        await db.execute("UPDATE users SET sub_until=? WHERE user_id=?", (new_until, user_id))
        await db.commit()
        return new_until


async def use_promo(code: str) -> int:
    """Returns days added, 0 if invalid"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_codes WHERE code=?", (code.lower(),)) as cur:
            row = await cur.fetchone()
        if not row or row["uses_left"] <= 0:
            return 0
        await db.execute(
            "UPDATE promo_codes SET uses_left=uses_left-1 WHERE code=?",
            (code.lower(),)
        )
        await db.commit()
        return row["days"]


# ── Accounts ──────────────────────────────────────────────────────────────────

async def get_accounts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchall()


async def get_account(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)) as cur:
            return await cur.fetchone()


async def create_account(user_id: int, phone: str, proxy: str = None,
                         api_id: int = None, api_hash: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO accounts (user_id, phone, proxy, api_id, api_hash) VALUES (?,?,?,?,?)",
            (user_id, phone, proxy, api_id, api_hash)
        )
        await db.commit()
        return cur.lastrowid


async def save_session(account_id: int, session_str: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET session=? WHERE id=?", (session_str, account_id))
        await db.commit()


async def delete_account(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        await db.commit()


# ── Mailings ──────────────────────────────────────────────────────────────────

async def get_mailings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM mailings WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchall()


async def get_mailing(mailing_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM mailings WHERE id=?", (mailing_id,)) as cur:
            return await cur.fetchone()


async def create_mailing(user_id: int, name: str, account_id: int,
                         interval: int, messages: str, chats: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO mailings (user_id,name,account_id,interval,messages,chats) VALUES (?,?,?,?,?,?)",
            (user_id, name, account_id, interval, messages, chats)
        )
        await db.commit()
        return cur.lastrowid


async def update_mailing_status(mailing_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE mailings SET status=? WHERE id=?", (status, mailing_id))
        await db.commit()


async def delete_mailing(mailing_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM mailings WHERE id=?", (mailing_id,))
        await db.commit()


async def increment_sent(mailing_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE mailings SET sent_count=sent_count+1 WHERE id=?", (mailing_id,))
        await db.commit()


# ── Referrals ─────────────────────────────────────────────────────────────────

async def get_referrals(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT r.*, u.username FROM referrals r LEFT JOIN users u ON r.ref_user=u.user_id WHERE r.ref_by=?",
            (user_id,)
        ) as cur:
            return await cur.fetchall()
