"""
Database layer for Telegram Member Tag & Identification Bot
=============================================================
Manages SQLite storage for group member caching, native Telegram custom titles,
and custom member tags.
"""

import sqlite3
import os
import datetime
from typing import Optional, List, Dict, Any

from contextlib import contextmanager

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tags.db")


@contextmanager
def get_connection(db_path: str = DB_FILE):
    """Create and yield a thread-safe database connection, ensuring it closes on exit."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str = DB_FILE):
    """Initialize database tables and indexes."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Groups table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Members cache table (tracks users seen speaking or in admin list)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                username_lower TEXT,
                first_name TEXT,
                last_name TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                tag_name TEXT NOT NULL,
                tag_name_lower TEXT NOT NULL,
                source TEXT DEFAULT 'custom', -- 'custom' (bot command) or 'native' (Telegram custom title)
                assigned_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (chat_id, tag_name_lower)
            )
        """)

        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_user ON members (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_username ON members (chat_id, username_lower);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_lookup ON tags (tag_name_lower);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_chat_user ON tags (chat_id, user_id);")

        conn.commit()


def upsert_group(chat_id: int, title: str, db_path: str = DB_FILE):
    """Insert or update group information."""
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO groups (chat_id, title, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                updated_at = CURRENT_TIMESTAMP
        """, (chat_id, title))
        conn.commit()


def upsert_member(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
    db_path: str = DB_FILE
):
    """Insert or update member information in the group cache."""
    clean_username = username.lstrip("@").strip() if username else None
    username_lower = clean_username.lower() if clean_username else None

    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO members (chat_id, user_id, username, username_lower, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = COALESCE(excluded.username, members.username),
                username_lower = COALESCE(excluded.username_lower, members.username_lower),
                first_name = COALESCE(excluded.first_name, members.first_name),
                last_name = COALESCE(excluded.last_name, members.last_name),
                last_seen = CURRENT_TIMESTAMP
        """, (chat_id, user_id, clean_username, username_lower, first_name or "", last_name or ""))
        conn.commit()


def find_member_by_username(chat_id: Optional[int], username: str, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    """Look up a member by @username."""
    clean_name = username.lstrip("@").strip().lower()
    with get_connection(db_path) as conn:
        if chat_id is not None:
            row = conn.execute("""
                SELECT * FROM members
                WHERE chat_id = ? AND username_lower = ?
                ORDER BY last_seen DESC LIMIT 1
            """, (chat_id, clean_name)).fetchone()
        else:
            row = conn.execute("""
                SELECT * FROM members
                WHERE username_lower = ?
                ORDER BY last_seen DESC LIMIT 1
            """, (clean_name,)).fetchone()

        return dict(row) if row else None


def find_member_by_id(chat_id: Optional[int], user_id: int, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    """Look up a member by Telegram user ID."""
    with get_connection(db_path) as conn:
        if chat_id is not None:
            row = conn.execute("""
                SELECT * FROM members
                WHERE chat_id = ? AND user_id = ?
                LIMIT 1
            """, (chat_id, user_id)).fetchone()
        else:
            row = conn.execute("""
                SELECT * FROM members
                WHERE user_id = ?
                ORDER BY last_seen DESC LIMIT 1
            """, (user_id,)).fetchone()

        return dict(row) if row else None


def set_tag(
    chat_id: int,
    user_id: int,
    tag_name: str,
    source: str = "custom",
    assigned_by: Optional[int] = None,
    db_path: str = DB_FILE
) -> Dict[str, Any]:
    """
    Assign a tag to a user in a group.
    If the tag already exists in this group, reassigns it to this user.
    """
    clean_tag = tag_name.strip()
    tag_lower = clean_tag.lower()

    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO tags (chat_id, user_id, tag_name, tag_name_lower, source, assigned_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, tag_name_lower) DO UPDATE SET
                user_id = excluded.user_id,
                tag_name = excluded.tag_name,
                source = excluded.source,
                assigned_by = excluded.assigned_by,
                created_at = CURRENT_TIMESTAMP
        """, (chat_id, user_id, clean_tag, tag_lower, source, assigned_by))
        conn.commit()

    return {"chat_id": chat_id, "user_id": user_id, "tag_name": clean_tag, "source": source}


def remove_tag(chat_id: int, tag_name: str, db_path: str = DB_FILE) -> bool:
    """Remove a tag by name in a specific group."""
    tag_lower = tag_name.strip().lower()
    with get_connection(db_path) as conn:
        cur = conn.execute("""
            DELETE FROM tags
            WHERE chat_id = ? AND tag_name_lower = ?
        """, (chat_id, tag_lower))
        conn.commit()
        return cur.rowcount > 0


def remove_tags_for_user(chat_id: int, user_id: int, db_path: str = DB_FILE) -> int:
    """Remove all custom tags for a specific user in a group."""
    with get_connection(db_path) as conn:
        cur = conn.execute("""
            DELETE FROM tags
            WHERE chat_id = ? AND user_id = ? AND source = 'custom'
        """, (chat_id, user_id))
        conn.commit()
        return cur.rowcount


def get_user_by_tag(
    tag_name: str,
    chat_id: Optional[int] = None,
    db_path: str = DB_FILE
) -> List[Dict[str, Any]]:
    """
    Find user(s) matching a tag name (case-insensitive).
    Returns a list of match dicts with user info, group title, and source.
    """
    tag_lower = tag_name.strip().lower()

    with get_connection(db_path) as conn:
        query = """
            SELECT 
                t.id AS tag_id,
                t.chat_id,
                t.user_id,
                t.tag_name,
                t.source,
                t.created_at AS tagged_at,
                m.username,
                m.first_name,
                m.last_name,
                g.title AS group_title
            FROM tags t
            LEFT JOIN members m ON (t.chat_id = m.chat_id AND t.user_id = m.user_id)
            LEFT JOIN groups g ON t.chat_id = g.chat_id
            WHERE t.tag_name_lower = ?
        """
        params: List[Any] = [tag_lower]

        if chat_id is not None:
            query += " AND t.chat_id = ?"
            params.append(chat_id)

        query += " ORDER BY t.created_at DESC"
        rows = conn.execute(query, params).fetchall()

        # If members table didn't have the user for that specific chat, try global member record
        results = []
        for r in rows:
            d = dict(r)
            if not d["username"] and not d["first_name"]:
                # Try finding across any chat
                fallback = conn.execute("""
                    SELECT username, first_name, last_name
                    FROM members
                    WHERE user_id = ? AND (username IS NOT NULL OR first_name != '')
                    ORDER BY last_seen DESC LIMIT 1
                """, (d["user_id"],)).fetchone()
                if fallback:
                    d["username"] = fallback["username"]
                    d["first_name"] = fallback["first_name"]
                    d["last_name"] = fallback["last_name"]
            results.append(d)

        return results


def search_tags_fuzzy(
    query_text: str,
    chat_id: Optional[int] = None,
    db_path: str = DB_FILE
) -> List[Dict[str, Any]]:
    """Search for tags that contain query_text."""
    q = f"%{query_text.strip().lower()}%"
    with get_connection(db_path) as conn:
        query = """
            SELECT 
                t.id AS tag_id,
                t.chat_id,
                t.user_id,
                t.tag_name,
                t.source,
                m.username,
                m.first_name,
                m.last_name,
                g.title AS group_title
            FROM tags t
            LEFT JOIN members m ON (t.chat_id = m.chat_id AND t.user_id = m.user_id)
            LEFT JOIN groups g ON t.chat_id = g.chat_id
            WHERE t.tag_name_lower LIKE ?
        """
        params: List[Any] = [q]
        if chat_id is not None:
            query += " AND t.chat_id = ?"
            params.append(chat_id)
        query += " ORDER BY t.tag_name_lower ASC LIMIT 10"

        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_tags_for_user(chat_id: int, user_id: int, db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Return all tags assigned to a specific user in a group."""
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT tag_name, source, created_at
            FROM tags
            WHERE chat_id = ? AND user_id = ?
            ORDER BY created_at DESC
        """, (chat_id, user_id)).fetchall()
        return [dict(r) for r in rows]


def get_all_tags_in_group(chat_id: int, db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Return all tags registered in a specific group."""
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT 
                t.tag_name,
                t.user_id,
                t.source,
                t.created_at,
                m.username,
                m.first_name,
                m.last_name
            FROM tags t
            LEFT JOIN members m ON (t.chat_id = m.chat_id AND t.user_id = m.user_id)
            WHERE t.chat_id = ?
            ORDER BY t.tag_name_lower ASC
        """, (chat_id,)).fetchall()
        return [dict(r) for r in rows]


def sync_native_admin_tags(chat_id: int, admin_members: List[Dict[str, Any]], db_path: str = DB_FILE) -> int:
    """
    Synchronize Telegram native custom titles for a group.
    Replaces all 'native' source tags for this group with the current admin list.
    admin_members is a list of dicts:
    [{'user_id': ..., 'custom_title': ..., 'username': ..., 'first_name': ..., 'last_name': ...}]
    """
    with get_connection(db_path) as conn:
        # Clear previous native tags for this group
        conn.execute("DELETE FROM tags WHERE chat_id = ? AND source = 'native'", (chat_id,))

        count = 0
        for adm in admin_members:
            title = adm.get("custom_title")
            user_id = adm.get("user_id")
            if not title or not user_id:
                continue

            clean_title = title.strip()
            if not clean_title:
                continue

            # Update member cache using existing connection
            c_user = adm.get("username")
            clean_username = c_user.lstrip("@").strip() if c_user else None
            username_lower = clean_username.lower() if clean_username else None
            f_name = adm.get("first_name") or ""
            l_name = adm.get("last_name") or ""

            conn.execute("""
                INSERT INTO members (chat_id, user_id, username, username_lower, first_name, last_name, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, members.username),
                    username_lower = COALESCE(excluded.username_lower, members.username_lower),
                    first_name = COALESCE(excluded.first_name, members.first_name),
                    last_name = COALESCE(excluded.last_name, members.last_name),
                    last_seen = CURRENT_TIMESTAMP
            """, (chat_id, user_id, clean_username, username_lower, f_name, l_name))

            # Insert tag
            try:
                conn.execute("""
                    INSERT INTO tags (chat_id, user_id, tag_name, tag_name_lower, source, created_at)
                    VALUES (?, ?, ?, ?, 'native', CURRENT_TIMESTAMP)
                    ON CONFLICT(chat_id, tag_name_lower) DO UPDATE SET
                        user_id = excluded.user_id,
                        tag_name = excluded.tag_name,
                        source = 'native',
                        created_at = CURRENT_TIMESTAMP
                """, (chat_id, user_id, clean_title, clean_title.lower()))
                count += 1
            except Exception:
                pass
                pass

        conn.commit()
        return count
