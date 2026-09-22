"""
Telegram Member Tag & Identification Bot
==========================================
Identifies group members by custom tags/titles.
Supports both Telegram native Admin Custom Titles (auto-synced) and
bot-assigned tags for any member.
"""

import os
import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, List, Dict, Any

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
from telegram import Update, ChatMemberAdministrator, ChatMemberOwner
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

import database

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Master admin user ID (optional)
MASTER_ADMIN_ID = None
raw_master_id = os.getenv("ADMIN_USER_ID")
if raw_master_id and raw_master_id.isdigit():
    MASTER_ADMIN_ID = int(raw_master_id)


# ==========================================
# PERMISSION HELPERS
# ==========================================

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if the given user is an administrator in the current group or master admin."""
    if MASTER_ADMIN_ID and user_id == MASTER_ADMIN_ID:
        return True

    chat = update.effective_chat
    if not chat:
        return False

    if chat.type in ["group", "supergroup"]:
        try:
            member = await context.bot.get_chat_member(chat.id, user_id)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except Exception as e:
            logger.warning(f"Could not verify admin status for user {user_id} in {chat.id}: {e}")
            return False

    # In private chat: only allow if user is an admin of at least one monitored group
    with database.get_connection() as conn:
        groups = conn.execute("SELECT chat_id FROM groups").fetchall()
        for g in groups:
            try:
                member = await context.bot.get_chat_member(g["chat_id"], user_id)
                if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                    return True
            except Exception:
                continue

    return False


async def is_bot_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Check if the bot itself has administrator rights in the group."""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        return bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.debug(f"Error checking bot admin status in chat {chat_id}: {e}")
        return False


async def sync_native_titles(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetch all group admins and sync their native custom titles into the database."""
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_data = []
        for adm in admins:
            user = adm.user
            custom_title = getattr(adm, "custom_title", None)
            admin_data.append({
                "user_id": user.id,
                "custom_title": custom_title,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            })

        count = database.sync_native_admin_tags(chat_id, admin_data)
        return count
    except Exception as e:
        logger.warning(f"Could not sync native admin titles for chat {chat_id}: {e}")
        return 0


# ==========================================
# COMMAND HANDLERS
# ==========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    chat = update.effective_chat

    if chat.type == "private":
        text = (
            f"👋 Hello, **{user.first_name}**!\n\n"
            "I am the **Member Tag & Identification Bot**.\n"
            "I help you organize, tag, and identify members in your Telegram groups.\n\n"
            "**Key Features:**\n"
            "• 🔍 **Tag Identification:** Type `/whois <tag>` to instantly find who holds that tag.\n"
            "• 🏷️ **Native Custom Titles:** Automatically reads titles you give members in Telegram settings.\n"
            "• ✍️ **Bot-Assigned Tags:** Assign tags to any member using `/tag <tag>`.\n"
            "• 📋 **Directory:** View all tagged members with `/tags`.\n\n"
            "**Getting Started:**\n"
            "1. Add me to your group.\n"
            "2. Make me an **Administrator** in the group.\n"
            "3. Start tagging members with `/tag` or assign custom titles in Telegram!"
        )
    else:
        text = (
            f"👋 Hello! I am active in **{chat.title}**.\n"
            "• Use `/whois <tag>` to identify who has a tag.\n"
            "• Use `/tag <tag>` (reply to a message) to assign a tag.\n"
            "• Use `/tags` to list all tagged members in this group."
        )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the complete command reference."""
    help_text = (
        "📖 **Member Tag Bot — Command Guide**\n\n"
        "**Identifying Members:**\n"
        "• `/whois <tag>` or `/find <tag>`\n"
        "  Identifies the user with that tag (gives @username, name, ID, and profile link).\n"
        "  *(Works inside the group or privately in my DM)*\n\n"
        "• `/user [@username or reply]`\n"
        "  Displays what tag(s) are assigned to a member.\n\n"
        "• `/tags` or `/listtags`\n"
        "  Lists all tagged members in the group.\n\n"
        "**Managing Tags (Group Admins Only):**\n"
        "• `/tag <tag_name>`\n"
        "  *Reply to a member's message* to give them a tag (e.g. `/tag jacob`).\n\n"
        "• `/tag @username <tag_name>`\n"
        "  Assigns a tag to a member by their @username.\n\n"
        "• `/untag <tag_name>`\n"
        "  Removes a tag from the group.\n\n"
        "• `/synctags`\n"
        "  Re-scans all Telegram native Custom Titles from group admins.\n\n"
        "• `/id`\n"
        "  Shows your user ID and group chat ID."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show chat and user ID."""
    chat = update.effective_chat
    user = update.effective_user
    text = (
        f"📋 **ID Information:**\n"
        f"• **Chat:** {chat.title or chat.first_name or 'N/A'}\n"
        f"• **Chat ID:** `{chat.id}`\n"
        f"• **Chat Type:** `{chat.type}`\n"
        f"• **Your User ID:** `{user.id}`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Assign a tag to a member.
    Usage:
      - By reply: /tag <tag_name>
      - By username: /tag @username <tag_name>
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    if chat.type not in ["group", "supergroup"]:
        await msg.reply_text("ℹ️ The `/tag` command must be used inside a group.", parse_mode=ParseMode.MARKDOWN)
        return

    # Check admin permission
    if not await is_user_admin(update, context, user.id):
        await msg.reply_text("⛔ Only group administrators can assign tags.")
        return

    target_user_id = None
    target_username = None
    target_first_name = None
    target_last_name = None
    tag_name = None

    # Case 1: Reply to a user's message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target_user = msg.reply_to_message.from_user
        if target_user.is_bot:
            await msg.reply_text("⚠️ Cannot assign tags to bots.")
            return

        if not context.args or len(context.args) < 1:
            await msg.reply_text("ℹ️ Please provide the tag name:\nReply to a message with `/tag <name>` (e.g. `/tag jacob`).", parse_mode=ParseMode.MARKDOWN)
            return

        tag_name = " ".join(context.args).strip()
        target_user_id = target_user.id
        target_username = target_user.username
        target_first_name = target_user.first_name
        target_last_name = target_user.last_name

    # Case 2: Mentioned username in args: /tag @username <tag>
    elif context.args and len(context.args) >= 2 and context.args[0].startswith("@"):
        input_username = context.args[0].lstrip("@").strip()
        tag_name = " ".join(context.args[1:]).strip()

        # Look up in database cache
        member_record = database.find_member_by_username(chat.id, input_username)
        if not member_record:
            # Fallback across all chats
            member_record = database.find_member_by_username(None, input_username)

        if member_record:
            target_user_id = member_record["user_id"]
            target_username = member_record["username"]
            target_first_name = member_record["first_name"]
            target_last_name = member_record["last_name"]
        else:
            await msg.reply_text(
                f"⚠️ I haven't seen `@{input_username}` in this group yet.\n\n"
                "💡 **Tip:** Simply reply to one of their messages with `/tag " + tag_name + "` to tag them directly!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        await msg.reply_text(
            "ℹ️ **How to assign a tag:**\n\n"
            "1. **Reply to their message:**\n"
            "   `/tag jacob`\n\n"
            "2. **Or by username:**\n"
            "   `/tag @username jacob`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Clean tag formatting
    tag_name = tag_name.lstrip("#").strip()
    if not tag_name:
        await msg.reply_text("❌ Invalid tag name.")
        return

    # Cache target user details
    database.upsert_member(
        chat_id=chat.id,
        user_id=target_user_id,
        username=target_username,
        first_name=target_first_name,
        last_name=target_last_name
    )

    # Store tag
    database.set_tag(
        chat_id=chat.id,
        user_id=target_user_id,
        tag_name=tag_name,
        source="custom",
        assigned_by=user.id
    )

    handle = f"@{target_username}" if target_username else (target_first_name or f"User {target_user_id}")
    await msg.reply_text(
        f"✅ Tag **'{tag_name}'** successfully assigned to {handle}!\n\n"
        f"You can now find them anytime by typing `/whois {tag_name}`.",
        parse_mode=ParseMode.MARKDOWN
    )


async def untag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Remove a tag by name.
    Usage: /untag <tag_name>
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    if chat.type not in ["group", "supergroup"]:
        await msg.reply_text("ℹ️ The `/untag` command must be used inside a group.")
        return

    if not await is_user_admin(update, context, user.id):
        await msg.reply_text("⛔ Only group administrators can remove tags.")
        return

    if not context.args or len(context.args) < 1:
        await msg.reply_text("ℹ️ Usage: `/untag <tag_name>`", parse_mode=ParseMode.MARKDOWN)
        return

    tag_to_remove = " ".join(context.args).lstrip("#").strip()
    success = database.remove_tag(chat.id, tag_to_remove)

    if success:
        await msg.reply_text(f"🗑️ Tag **'{tag_to_remove}'** has been removed.", parse_mode=ParseMode.MARKDOWN)
    else:
        await msg.reply_text(f"⚠️ Tag **'{tag_to_remove}'** was not found in this group.", parse_mode=ParseMode.MARKDOWN)


async def whois_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Identify who has a given tag.
    Usage: /whois <tag_name> or /find <tag_name>
    Works in group and private chat.
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    if not await is_user_admin(update, context, user.id):
        await msg.reply_text("⛔ Only group administrators are permitted to look up tags.")
        return

    if not context.args or len(context.args) < 1:
        await msg.reply_text("ℹ️ Please provide the tag to search for.\nUsage: `/whois <tag>` (e.g. `/whois jacob`)", parse_mode=ParseMode.MARKDOWN)
        return

    query_tag = " ".join(context.args).lstrip("#").strip()

    # If inside a group, also sync native admin titles on the fly
    chat_id = chat.id if chat.type in ["group", "supergroup"] else None
    if chat_id:
        try:
            await sync_native_titles(chat_id, context)
        except Exception:
            pass

    # Lookup tag in database
    matches = database.get_user_by_tag(query_tag, chat_id=chat_id)

    if matches:
        responses = []
        for m in matches:
            username = f"@{m['username']}" if m.get("username") else "*(No @username set)*"
            full_name = f"{m.get('first_name', '')} {m.get('last_name', '')}".strip() or "Anonymous"
            user_id = m['user_id']
            tag_name = m['tag_name']
            source_label = "Telegram Admin Title" if m.get("source") == "native" else "Bot Tag"
            group_name = m.get("group_title") or "Group"

            info = (
                f"🏷️ **Tag:** `{tag_name}`\n"
                f"👤 **Username:** {username}\n"
                f"📛 **Name:** {full_name}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"👥 **Group:** {group_name}\n"
                f"📌 **Type:** {source_label}\n"
                f"🔗 **Profile:** [Direct Link](tg://user?id={user_id})"
            )
            responses.append(info)

        result_text = "🔍 **Match Found:**\n\n" + "\n\n---\n\n".join(responses)
        await msg.reply_text(result_text, parse_mode=ParseMode.MARKDOWN)
        return

    # If no exact match, try fuzzy matching
    suggestions = database.search_tags_fuzzy(query_tag, chat_id=chat_id)
    if suggestions:
        sug_names = list({s["tag_name"] for s in suggestions})[:5]
        sug_text = ", ".join([f"`{n}`" for n in sug_names])
        await msg.reply_text(
            f"❌ No exact match for tag **'{query_tag}'**.\n\n"
            f"💡 **Similar tags found:** {sug_text}\n"
            f"Try `/whois <tag>` with one of those names, or use `/tags` to see all tags.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await msg.reply_text(
            f"❌ No member found with tag **'{query_tag}'**.\n"
            "Use `/tags` to view all active tags.",
            parse_mode=ParseMode.MARKDOWN
        )


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    List all registered tags in the group.
    Usage: /tags or /listtags
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    if not await is_user_admin(update, context, user.id):
        await msg.reply_text("⛔ Only group administrators are permitted to view the tagged members directory.")
        return

    if chat.type not in ["group", "supergroup"]:
        await msg.reply_text("ℹ️ Use `/tags` inside a group to view its directory of tags.")
        return

    # Trigger native titles sync
    try:
        await sync_native_titles(chat.id, context)
    except Exception:
        pass

    all_tags = database.get_all_tags_in_group(chat.id)

    if not all_tags:
        await msg.reply_text(
            "📭 No tags are currently registered in this group.\n\n"
            "• Reply to a member with `/tag <name>` to assign a tag.\n"
            "• Or give admins a Custom Title in group settings and run `/synctags`!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    lines = [f"📋 **Tagged Members in {chat.title}:**\n"]
    for idx, item in enumerate(all_tags, start=1):
        tag = item["tag_name"]
        user_str = f"@{item['username']}" if item.get("username") else (item.get("first_name") or f"ID: {item['user_id']}")
        source_badge = "👑" if item.get("source") == "native" else "🏷️"
        lines.append(f"{idx}. `{tag}` → **{user_str}** {source_badge}")

    lines.append("\n_Legend: 👑 = Telegram Admin Title, 🏷️ = Custom Tag_")
    lines.append("Type `/whois <tag>` to inspect any user.")

    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Check what tag(s) belong to a specific user.
    Usage: /user @username or reply /user
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    if not await is_user_admin(update, context, user.id):
        await msg.reply_text("⛔ Only group administrators are permitted to check member tags.")
        return

    target_user_id = None
    target_handle = None

    if msg.reply_to_message and msg.reply_to_message.from_user:
        target_user = msg.reply_to_message.from_user
        target_user_id = target_user.id
        target_handle = f"@{target_user.username}" if target_user.username else target_user.first_name
    elif context.args and len(context.args) > 0 and context.args[0].startswith("@"):
        uname = context.args[0].lstrip("@").strip()
        rec = database.find_member_by_username(chat.id if chat.type in ["group", "supergroup"] else None, uname)
        if rec:
            target_user_id = rec["user_id"]
            target_handle = f"@{rec['username']}"
        else:
            await msg.reply_text(f"⚠️ User `@{uname}` was not found in the member cache.", parse_mode=ParseMode.MARKDOWN)
            return
    else:
        # Default to the sender themselves
        target_user_id = update.effective_user.id
        target_handle = update.effective_user.first_name

    tags = database.get_tags_for_user(chat.id, target_user_id) if chat.type in ["group", "supergroup"] else []
    if tags:
        tag_list = ", ".join([f"`{t['tag_name']}`" for t in tags])
        await msg.reply_text(f"👤 **{target_handle}** has tag(s): {tag_list}", parse_mode=ParseMode.MARKDOWN)
    else:
        await msg.reply_text(f"ℹ️ No tags are assigned to **{target_handle}** in this group.", parse_mode=ParseMode.MARKDOWN)


async def synctags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Force an immediate scan and sync of Telegram native Admin Custom Titles.
    Usage: /synctags
    """
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    if chat.type not in ["group", "supergroup"]:
        await msg.reply_text("ℹ️ The `/synctags` command must be used inside a group.")
        return

    if not await is_user_admin(update, context, user.id):
        await msg.reply_text("⛔ Only group administrators can run `/synctags`.")
        return

    status_msg = await msg.reply_text("🔄 Scanning group administrators and custom titles...")

    # Check if bot is admin
    if not await is_bot_admin(context, chat.id):
        await status_msg.edit_text(
            "⚠️ **Bot is not an Admin!**\n\n"
            "To read Telegram native Custom Titles, please promote this bot to Administrator in the group settings.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    count = await sync_native_titles(chat.id, context)
    await status_msg.edit_text(
        f"✅ **Sync Complete!**\n"
        f"Found and updated **{count}** Telegram Admin Custom Title(s).\n\n"
        f"Use `/tags` to view the full directory.",
        parse_mode=ParseMode.MARKDOWN
    )


# ==========================================
# EVENT LISTENERS (CACHE UPDATER)
# ==========================================

async def track_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cache active users and group information whenever someone sends a message."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or chat.type not in ["group", "supergroup"]:
        return

    # Update group record
    database.upsert_group(chat.id, chat.title or "Unnamed Group")

    # Update member record
    database.upsert_member(
        chat_id=chat.id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )


async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listen for member joins/promotions and sync custom titles."""
    result = update.chat_member
    if not result:
        return

    chat = result.chat
    user = result.new_chat_member.user

    # Cache user
    database.upsert_member(
        chat_id=chat.id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # If member promotion or title change occurred, trigger sync
    if isinstance(result.new_chat_member, (ChatMemberAdministrator, ChatMemberOwner)):
        try:
            await sync_native_titles(chat.id, context)
        except Exception:
            pass


# ==========================================
# MAIN APPLICATION
# ==========================================

# ==========================================
# CLOUD HEALTH CHECK SERVER (FOR RENDER / WEB SERVICES)
# ==========================================

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to satisfy Render web service health checks."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK: Telegram Member Tag Bot is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Keep logs clean from automated uptime pings
        pass


def start_health_check_server():
    """Start the lightweight HTTP server on the PORT assigned by Render."""
    port_str = os.getenv("PORT")
    if not port_str:
        return

    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health-check HTTP server running on port {port} for Render")
    except Exception as e:
        logger.warning(f"Could not start health check server: {e}")


def main():
    """Start the bot."""
    # Start health check server if PORT is provided (e.g. on Render)
    start_health_check_server()

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "=" * 65)
        print("❌ ERROR: BOT_TOKEN is not set!")
        print("Please set your BOT_TOKEN in the 'telegram_tag_bot/.env' file.")
        print("You can obtain a token by chatting with @BotFather on Telegram.")
        print("=" * 65 + "\n")
        return

    # Initialize SQLite database
    print("[INFO] Initializing database...")
    database.init_db()

    print("[INFO] Starting Telegram Member Tag & Identification Bot...")
    application = Application.builder().token(bot_token).build()

    # Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("tag", tag_command))
    application.add_handler(CommandHandler("settag", tag_command))
    application.add_handler(CommandHandler("untag", untag_command))
    application.add_handler(CommandHandler(["whois", "find", "lookup"], whois_command))
    application.add_handler(CommandHandler(["tags", "listtags"], tags_command))
    application.add_handler(CommandHandler("user", user_command))
    application.add_handler(CommandHandler("synctags", synctags_command))

    # Update members cache on any message
    application.add_handler(
        MessageHandler(
            (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP) & ~filters.COMMAND,
            track_group_message
        )
    )

    # Track member updates (promotions, custom title changes, joins)
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.CHAT_MEMBER))

    print("[SUCCESS] Bot is online and listening!")
    print("[INFO] Add the bot to your group and promote it to Admin to get started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
