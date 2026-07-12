# Multi-User Authorization System

## Overview
The bot now supports multiple authorized users while maintaining a centralized admin control system.

**Admin User**: The user whose ID is in the `CHAT_ID` environment variable  
**Authorized Users**: Users added by the admin via the `/adduser` command  
**Public Commands**: Available to anyone (e.g., `/myid`)  
**Protected Commands**: Only for authorized users  
**Admin Commands**: Only for admin or users with admin flag  

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────┐
│   Database: authorized_users table      │
├─────────────────────────────────────────┤
│ user_id | username | is_admin | status │
├─────────────────────────────────────────┤
│ 123456  | admin    | true     | active │
│ 987654  | john     | false    | active │
│ 555555  | disabled_user | false | disabled │
└─────────────────────────────────────────┘
```

### User Workflow

#### **Step 1: New User Gets Their ID**
```
User: /myid

Bot Response:
👤 *Your Account Info:*

🆔 User ID: 987654321
📝 Username: @john_doe
👋 Name: John

_Share this ID with the admin to use the bot_
```

#### **Step 2: User Shares ID with Admin**
User sends admin their ID: `987654321`

#### **Step 3: Admin Adds User**
```
Admin: /adduser 987654321 john_doe

Bot Response:
✅ User `987654321` added successfully
```

#### **Step 4: User Can Now Use Bot**
```
User: /start

Bot Response:
🤖 *Amazon Price Tracker*
[Full menu and functionality available]
```

---

## Commands

### Public Commands (No Auth Required)

#### `/myid`
Get your Telegram user ID and account info
```
/myid
```
**Response**: Shows user ID, username, and name

---

### Protected Commands (Auth Required)

#### `/start`
Start the bot and show main menu
```
/start
```

#### `/track <url>`
Add a product to track
```
/track https://www.amazon.com.eg/dp/B0G2Y61HCP
/track https://amzn.eu/d/00rKyOJw
```

#### `/list`
Show all tracked products
```
/list
```

#### `/untrack <id>`
Remove a product from tracking
```
/untrack 1
```

#### `/check`
Manually check prices now
```
/check
```

---

### Admin Commands (Admin Only)

#### `/adduser <user_id> [username]`
Add a new authorized user
```
/adduser 987654321 john
/adduser 555555555 jane_doe
```

**Parameters**:
- `user_id` (required): Telegram user ID
- `username` (optional): User's Telegram username

**Response**:
```
✅ User `987654321` added successfully
```

#### `/removeuser <user_id>`
Disable/remove a user (marks as disabled, not deleted)
```
/removeuser 987654321
```

**Response**:
```
✅ User `987654321` removed
```

#### `/users`
List all authorized active users
```
/users
```

**Response**:
```
👥 *Authorized Users:*

👑 🆔 123456789
📝 @admin_user
📅 2026-07-12 10:30:00

🆔 987654321
📝 @john_doe
📅 2026-07-12 11:45:00
```

---

## Authorization Checks

### User Authorization Flow

```python
def is_user_auth(user_id: int) -> bool:
    """Check if user is authorized"""
    return user_id == ADMIN_ID or is_user_authorized(user_id)
```

**User is authorized if**:
- ✅ They are the primary admin (CHAT_ID)
- ✅ They are in the authorized_users table with status='active'

### Admin Check Flow

```python
def is_user_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id == ADMIN_ID or is_admin(user_id)
```

**User is admin if**:
- ✅ They are the primary admin (CHAT_ID)
- ✅ They have is_admin=true in authorized_users table

---

## Database Schema

### authorized_users Table

```sql
CREATE TABLE authorized_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    authorized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active'
)
```

**Fields**:
- `user_id`: Telegram user ID (unique)
- `username`: Telegram username (optional)
- `is_admin`: Whether user has admin privileges
- `authorized_at`: When user was authorized
- `status`: 'active' or 'disabled'

---

## Database Functions

### Authorization Functions

```python
is_user_authorized(user_id: int) -> bool
# Check if user is in authorized list and active

is_admin(user_id: int) -> bool
# Check if user has admin flag

add_authorized_user(user_id, username=None, is_admin_flag=False)
# Add a new authorized user

remove_authorized_user(user_id)
# Disable a user (mark as disabled)

get_authorized_users() -> list
# Get all active authorized users

get_user_info(user_id) -> tuple
# Get info about a specific user
```

---

## Features

✅ **Single Point of Control**: Admin controls all user access  
✅ **No Database Per User**: Global products database, all shared  
✅ **Flexible Authorization**: Add/remove users without restarting  
✅ **Audit Trail**: Track when users were authorized  
✅ **Disable Without Delete**: Soft delete (mark disabled, not remove)  
✅ **Multi-Admin Support**: Can promote users to admin  
✅ **Bilingual**: Full Arabic/English support  
✅ **User-Friendly**: Simple `/myid` command for getting ID  

---

## Example Scenario

### Admin Setup

**Admin User ID**: 123456789 (in .env as CHAT_ID)

**Day 1**: Admin starts bot
```
Admin: /start
Bot: Welcome! You are authorized.
```

**Day 2**: Friend wants to use bot
```
Friend: /myid
Bot: Your User ID: 987654321

Friend: (sends ID to Admin via WhatsApp)

Admin: /adduser 987654321 friend_name
Bot: ✅ User 987654321 added successfully

Friend: /start
Bot: Welcome! Bot is ready to use.
```

**Day 3**: View all users
```
Admin: /users
Bot: Shows list of all authorized users
```

**Day 10**: Need to revoke access
```
Admin: /removeuser 987654321
Bot: ✅ User 987654321 removed

Friend: /start
Bot: ❌ You are not authorized
```

---

## Security Notes

⚠️ **Admin ID**: Keep your `CHAT_ID` in `.env` secret  
⚠️ **User IDs**: Only authorized admins can add users  
⚠️ **Status Column**: Disabled users cannot use bot, but records remain  
⚠️ **No Passwords**: Relies on Telegram's user ID system (sufficient for bot context)  

---

## Localization

All messages are available in:
- 🇬🇧 **English**
- 🇸🇦 **Arabic (العربية)**

Users can switch language with 🌐 button in main menu.

---

## Migration Notes

If upgrading from single-user version:
- `authorized_users` table is created automatically
- Primary admin (CHAT_ID) is implicit (no entry needed)
- Existing products database is preserved unchanged
- No data loss during migration
