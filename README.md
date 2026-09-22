# 🏷️ Telegram Member Tag & Identification Bot

A dedicated Telegram bot that remembers and identifies group members by custom tags/titles. 

Whenever you give a member a tag (for instance `'jacob'`) and later want to know who that person is in case you forget, you can ask the bot `/whois jacob` (or `/find jacob`). The bot will instantly return their **@username**, **Full Name**, **Telegram User ID**, and a direct link to their profile!

---

## ⚡ Quick Setup Guide

### 1. Create a Bot in Telegram
1. Open [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot` and follow the prompts to choose a name and username for your bot.
3. BotFather will give you an **API Token** (e.g. `123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ`).

### 2. Configure Token in `.env`
1. Open [`.env`](file:///c:/Users/Quality%20Assurance%20PC/Desktop/lfg/zesty/telegram_tag_bot/.env) inside `telegram_tag_bot/`.
2. Paste your bot token:
   ```env
   BOT_TOKEN=123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ
   ```

### 3. Start the Bot
Double-click [`run.bat`](file:///c:/Users/Quality%20Assurance%20PC/Desktop/lfg/zesty/telegram_tag_bot/run.bat) or run from PowerShell:
```powershell
.\run.bat
```

### 4. Add the Bot to Your Group
1. Add the bot to your Telegram group.
2. **Promote the bot to Administrator** in the group so it can read Telegram native custom titles and monitor member updates.
   *(The bot does not need dangerous permissions like ban or pin messages—basic admin rights are sufficient).*

---

## 🚀 How to Use

### 1. Tagging Members

There are two ways you can tag members:

#### Method A: Assign Custom Tags via Bot Command
* **By Replying (Easiest):**  
  Reply to any message from the member and type:
  ```
  /tag jacob
  ```
* **By Username:**  
  ```
  /tag @username jacob
  ```

#### Method B: Telegram Native Admin "Custom Title"
* In Telegram's Group Settings > Administrators:
  * Add a member as an admin (even with all permissions turned off).
  * Set their **Custom Title** to `jacob`.
  * The bot automatically detects this, or you can force a sync anytime with `/synctags`!

---

### 2. Identifying Members by Tag

Whenever you need to know who has a tag:

* In the group OR in a private DM with the bot, send:
  ```
  /whois jacob
  ```
  *(Aliases: `/find jacob`, `/lookup jacob`)*

**Bot Response Example:**
> 🔍 **Match Found:**  
> 🏷️ **Tag:** `jacob`  
> 👤 **Username:** `@jacob_miller`  
> 📛 **Name:** Jacob Miller  
> 🆔 **User ID:** `987654321`  
> 👥 **Group:** VIP Community  
> 📌 **Type:** Telegram Admin Title  
> 🔗 **Profile:** [Direct Link](tg://user?id=987654321)

---

## 🛠️ Complete Command Reference

| Command | Where to Run | Description |
|---|---|---|
| `/whois <tag>` | Group or Private DM | Identifies the member holding `<tag>` (gives username, name, ID, and profile link). |
| `/find <tag>` | Group or Private DM | Alias for `/whois`. |
| `/tag <tag>` | Group (replying to message) | Assigns `<tag>` to the replied member. |
| `/tag @user <tag>` | Group | Assigns `<tag>` to the mentioned `@user`. |
| `/untag <tag>` | Group | Removes `<tag>` from the group. |
| `/tags` or `/listtags` | Group | Displays a directory of all tagged members in the group. |
| `/user [@user or reply]` | Group or Private DM | Checks what tag(s) belong to a specific user. |
| `/synctags` | Group (Admins only) | Scans and updates all Telegram native custom titles from group admins. |
| `/id` | Anywhere | Displays your user ID and group chat ID. |
| `/help` | Anywhere | Displays the help and setup manual. |

---

## 💡 Pro-Tips
* **Search is Case-Insensitive:** `/whois jacob`, `/whois Jacob`, and `/whois JACOB` all find the exact same user.
* **Similar Tag Suggestions:** If you make a typo like `/whois jaco`, the bot will automatically suggest similar existing tags like `jacob`!
* **Private DM Lookups:** You can privately DM your bot `/whois jacob` without needing to ask inside the group.
