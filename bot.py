import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from database import (
    init_db, add_product, add_user_product, remove_user_product, get_all_products,
    get_user_products, remove_product, get_product_by_id, get_product_by_url,
    is_user_authorized, is_admin, add_authorized_user, remove_authorized_user,
    get_authorized_users, get_user_language, set_user_language, get_price_history
)
from scraper import fetch_product
from scheduler import start_scheduler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ADMIN_ID = int(CHAT_ID) if CHAT_ID else None
INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))

TRANSLATIONS = {
    "en": {
        "help_title": "🤖 *Amazon Price Tracker*",
        "help_desc": "Track product prices and get automatic updates!",
        "help_commands": "_Commands available:_",
        "track_cmd": "• 📦 `/track <url>` - Add a product",
        "list_cmd": "• 🧾 `/list` - Show tracked products",
        "check_cmd": "• 🔎 `/check` - Check prices now",
        "untrack_cmd": "• 🗑 `/untrack <id>` - Remove a product",
        "help_lang": "_Supported link formats:_",
        "lang_full": "• Full: `https://www.amazon.com.eg/...`",
        "lang_short": "• Shortened: `https://amzn.eu/d/...`",
        "language": "Language",
        "english": "English",
        "arabic": "العربية",
        "added_success": "✅ *Successfully Added!*",
        "current_price": "Current Price",
        "price_updates": "You'll receive updates when the price changes.",
        "check_list": "Check your list anytime with 🧾 or `/list`",
        "tracked_products": "Tracked Products",
        "no_products": "No products tracked yet.",
        "add_first": "Use 📦 to add your first product!",
        "send_link": "Send me the product link to track it.",
        "full_link": "Full: `https://www.amazon.com.eg/...`",
        "short_link": "Short: `https://amzn.eu/d/00rKyOJw`",
        "paste_link": "Just paste the link and I'll add it to your list!",
        "remove_product": "Remove a product from tracking",
        "product_id": "Send me the product ID",
        "see_list_first": "(use 🧾 to see your list first)",
        "example": "Example",
        "remove_from": "No longer monitoring",
        "invalid_url": "Invalid URL",
        "provide_link": "Please provide a valid Amazon product link.",
        "not_amazon": "Not an Amazon link",
        "not_amazon_desc": "This doesn't look like an Amazon URL.\nPlease make sure you're sharing a product from Amazon.",
        "fetching": "Fetching product details...",
        "please_wait": "Please wait...",
        "could_not_fetch": "Could not fetch the product",
        "link_invalid": "The link might be invalid, or Amazon is temporarily blocking requests.",
        "try_tips": "Try:\n• Copy the link from your browser address bar\n• Wait a moment and try again\n• Check the product still exists",
        "lang_updated": "Language Updated",
        "select_language": "Select Language",
        "choose_language": "Choose your preferred language for the bot:",
    },
    "ar": {
        "help_title": "🤖 *تتبع أسعار أمازون*",
        "help_desc": "تتبع أسعار المنتجات واحصل على تحديثات تلقائية!",
        "help_commands": "_الأوامر المتاحة:_",
        "track_cmd": "• 📦 `/track <رابط>` - إضافة منتج",
        "list_cmd": "• 🧾 `/list` - عرض المنتجات المتتبعة",
        "check_cmd": "• 🔎 `/check` - فحص الأسعار الآن",
        "untrack_cmd": "• 🗑 `/untrack <رقم>` - إزالة منتج",
        "help_lang": "_تنسيقات الروابط المدعومة:_",
        "lang_full": "• كامل: `https://www.amazon.com.eg/...`",
        "lang_short": "• مختصر: `https://amzn.eu/d/...`",
        "language": "اللغة",
        "english": "English",
        "arabic": "العربية",
        "added_success": "✅ *تمت الإضافة بنجاح!*",
        "current_price": "السعر الحالي",
        "price_updates": "ستتلقى تحديثات عند تغيير السعر.",
        "check_list": "تحقق من قائمتك في أي وقت باستخدام 🧾 أو `/list`",
        "tracked_products": "المنتجات المتتبعة",
        "no_products": "لا توجد منتجات مراقبة حاليًا.",
        "add_first": "استخدم 📦 لإضافة أول منتج!",
        "send_link": "أرسل لي رابط المنتج لتتبعه.",
        "full_link": "كامل: `https://www.amazon.com.eg/...`",
        "short_link": "مختصر: `https://amzn.eu/d/00rKyOJw`",
        "paste_link": "ما عليك سوى لصق الرابط وسأضيفه إلى قائمتك!",
        "remove_product": "إزالة منتج من المراقبة",
        "product_id": "أرسل لي معرّف المنتج",
        "see_list_first": "(استخدم 🧾 لرؤية قائمتك أولاً)",
        "example": "مثال",
        "remove_from": "لم يعد قيد المراقبة",
        "invalid_url": "رابط غير صالح",
        "provide_link": "يرجى توفير رابط منتج أمازون صالح.",
        "not_amazon": "ليس رابط أمازون",
        "not_amazon_desc": "هذا لا يبدو أنه رابط أمازون.\nتأكد من مشاركتك منتجًا من أمازون.",
        "fetching": "جاري جلب تفاصيل المنتج...",
        "please_wait": "يرجى الانتظار...",
        "could_not_fetch": "تعذر جلب المنتج",
        "link_invalid": "قد يكون الرابط غير صالح، أو أمازون تحجب الطلب مؤقتًا.",
        "try_tips": "جرب:\n• انسخ الرابط من شريط عنوان متصفحك\n• انتظر قليلاً ثم حاول مرة أخرى\n• تحقق من أن المنتج لا يزال موجودًا",
        "lang_updated": "تم تحديث اللغة",
        "select_language": "اختر اللغة",
        "choose_language": "اختر لغتك المفضلة للروبوت:",
    }
}


def get_text(lang: str, key: str) -> str:
    """Get translated text for a key."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, "")


def validate_config() -> None:
    missing = []
    if not TOKEN:
        missing.append("TELEGRAM_TOKEN")
    if not CHAT_ID:
        missing.append("CHAT_ID")

    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Avoid leaking bot token in HTTP request URLs at INFO level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def build_help_message(lang: str = "en") -> str:
    return (
        f"{get_text(lang, 'help_title')}\n\n"
        f"{get_text(lang, 'help_desc')}\n\n"
        f"{get_text(lang, 'help_commands')}\n"
        f"{get_text(lang, 'track_cmd')}\n"
        f"{get_text(lang, 'list_cmd')}\n"
        f"{get_text(lang, 'check_cmd')}\n"
        f"{get_text(lang, 'untrack_cmd')}\n\n"
        f"{get_text(lang, 'help_lang')}\n"
        f"{get_text(lang, 'lang_full')}\n"
        f"{get_text(lang, 'lang_short')}"
    )


def build_menu_markup(lang: str = "en", user_id: int | None = None) -> InlineKeyboardMarkup:
    track_btn = "📦 أضف منتج" if lang == "ar" else "📦 Add Product"
    list_btn = "🧾 منتجاتي" if lang == "ar" else "🧾 My Products"
    check_btn = "🔎 افحص الآن" if lang == "ar" else "🔎 Check Now"
    remove_btn = "❌ إزالة" if lang == "ar" else "❌ Remove"
    help_btn = "❓ المساعدة" if lang == "ar" else "❓ Help & Info"
    lang_btn = "🌐 اللغة" if lang == "ar" else "🌐 Language"

    keyboard = [
        [
            InlineKeyboardButton(track_btn, callback_data="track"),
            InlineKeyboardButton(list_btn, callback_data="list"),
        ],
        [
            InlineKeyboardButton(check_btn, callback_data="check"),
            InlineKeyboardButton(remove_btn, callback_data="untrack"),
        ],
        [
            InlineKeyboardButton(help_btn, callback_data="help"),
            InlineKeyboardButton(lang_btn, callback_data="language"),
        ],
    ]

    user_is_admin = user_id == ADMIN_ID or (user_id and is_admin(user_id))
    if user_is_admin:
        admin_btn = "⚙️ إدارة" if lang == "ar" else "⚙️ Admin"
        keyboard.append([InlineKeyboardButton(admin_btn, callback_data="admin_menu")])

    return InlineKeyboardMarkup(keyboard)


def build_tracking_success_message(product_name: str, price: float, lang: str = "en") -> str:
    if lang == "ar":
        return (
            f"✅ *تمت الإضافة بنجاح!*\n\n"
            f"📦 *{product_name}*\n"
            f"💰 السعر الحالي: `EGP {price:,.2f}`\n\n"
            f"_ستتلقى تحديثات عند تغيير السعر._\n"
            f"تحقق من قائمتك في أي وقت باستخدام 🧾 أو `/list`"
        )
    return (
        f"✅ *Successfully Added!*\n\n"
        f"📦 *{product_name}*\n"
        f"💰 Current Price: `EGP {price:,.2f}`\n\n"
        f"_You'll receive updates when the price changes._\n"
        f"Check your list anytime with 🧾 or `/list`"
    )


def build_products_list_message(products, lang: str = "en") -> str:
    if not products:
        if lang == "ar":
            return "📦 *المنتجات المتتبعة:*\n\nلا توجد منتجات مراقبة حاليًا."
        return "📦 *Tracked Products:*\n\nNo products tracked yet."

    if lang == "ar":
        lines = [f"📦 *المنتجات المتتبعة* ({len(products)})\n"]
        before_text = "السعر السابق"
        current_text = "السعر الحالي"
        added_text = "تاريخ الإضافة"
    else:
        lines = [f"📦 *Tracked Products* ({len(products)})\n"]
        before_text = "Before"
        current_text = "Current"
        added_text = "Added"

    for pid, url, name, last_price, prev_price, image_url, added_at, alert_threshold in products:
        current_str = f"EGP {last_price:,.2f}" if last_price is not None else "N/A"

        price_info = f"💰 {current_text}: `{current_str}`"
        if prev_price is not None and prev_price != last_price and last_price is not None:
            prev_str = f"EGP {prev_price:,.2f}"
            diff = last_price - prev_price
            pct = (diff / prev_price) * 100 if prev_price > 0 else 0
            emoji = "📉" if diff < 0 else "📈"
            price_info += f"\n{emoji} {before_text}: ~~`{prev_str}`~~ (±{abs(pct):.1f}%)"

        added_date = datetime.fromisoformat(added_at).strftime("%b %d") if added_at else "N/A"
        view_text = "عرض على أمازون" if lang == "ar" else "View on Amazon"
        lines.append(
            f"*{pid}.* {name}\n"
            f"{price_info}\n"
            f"📅 {added_text}: {added_date}\n"
            f"🔗 [{view_text}]({url})\n"
        )
    return "\n".join(lines)


def is_valid_amazon_url(url: str) -> bool:
    """Check if URL is a valid Amazon link in any supported format."""
    amazon_domains = [
        "amazon.com",
        "amazon.co",
        "amazon.de",
        "amazon.fr",
        "amazon.it",
        "amazon.es",
        "amazon.nl",
        "amazon.ca",
        "amazon.com.au",
        "amazon.com.br",
        "amazon.in",
        "amazon.jp",
        "amazon.sg",
        "amazon.ae",
        "amazon.sa",
        "amazon.eg",
        "amzn.",
    ]
    return any(domain in url for domain in amazon_domains)


def is_authorized(update: Update) -> bool:
    """Check if user is authorized (admin or authorized user)."""
    user_id = update.effective_user.id
    return user_id == ADMIN_ID or is_user_authorized(user_id)


def get_lang(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Resolve the user's language, falling back to the database.

    context.user_data lives in memory only, so it is empty after a restart —
    without the DB fallback every user silently reverts to English.
    """
    lang = context.user_data.get("language")
    if not lang:
        lang = get_user_language(user_id)
        context.user_data["language"] = lang
    return lang


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    if not is_authorized(update):
        keyboard = [
            [InlineKeyboardButton("📋 Copy User ID", callback_data="copy_user_id")],
            [InlineKeyboardButton("❓ Get Instructions", callback_data="get_instructions")],
        ]

        msg = (
            f"🚫 *Access Denied*\n\n"
            f"You are not authorized to use this bot yet.\n\n"
            f"📍 *Your User ID:*\n`{user_id}`\n\n"
            f"👤 *Your Username:*\n`@{username if username else 'Not set'}`\n\n"
            f"📬 *To get access:*\n"
            f"1. Copy your User ID above\n"
            f"2. Contact the bot admin\n"
            f"3. Send them your ID and desired display name\n"
            f"4. They will authorize you!\n\n"
            f"⏳ Once authorized, you'll be able to use all features."
        )
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"[bot] Unauthorized access attempt from {user_id} ({first_name})")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    if "language" not in context.user_data:
        context.user_data["language"] = get_user_language(user_id)

    context.user_data["awaiting_track_url"] = False
    context.user_data["awaiting_untrack_id"] = False
    lang = context.user_data["language"]

    await update.message.reply_text(
        build_help_message(lang),
        parse_mode="Markdown",
        reply_markup=build_menu_markup(lang, user_id)
    )


async def handle_unauthorized_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    action = query.data

    if action == "copy_user_id":
        await query.answer("✅ User ID copied to clipboard!", show_alert=False)
        msg = (
            f"📋 *Your User ID*\n\n"
            f"`{user_id}`\n\n"
            f"👉 Click the code above to copy it, then send it to the admin."
        )
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif action == "get_instructions":
        await query.answer()
        msg = (
            f"📖 *How to Get Access*\n\n"
            f"*Step 1:* Copy your User ID\n"
            f"`{user_id}`\n\n"
            f"*Step 2:* Find the admin\n"
            f"Ask in the group chat or contact them directly\n\n"
            f"*Step 3:* Send them:\n"
            f"• Your User ID (above)\n"
            f"• Your desired display name (e.g., 'Ahmed')\n\n"
            f"*Step 4:* They will authorize you using `/admin`\n\n"
            f"*Step 5:* Send `/start` again - you should now have access! ✅"
        )
        await query.edit_message_text(msg, parse_mode="Markdown")


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    action = query.data

    if action == "track":
        context.user_data["awaiting_track_url"] = True
        context.user_data["awaiting_untrack_id"] = False
        if lang == "ar":
            msg = ("📤 *أرسل لي رابط المنتج لتتبعه.*\n\n"
                   "_تنسيقات مدعومة:_\n"
                   "🔗 كامل: `https://www.amazon.com.eg/...`\n"
                   "⚡ مختصر: `https://amzn.eu/d/00rKyOJw`\n\n"
                   "_فقط ألصق الرابط وسأضيفه إلى قائمتك!_")
        else:
            msg = ("📤 *Send me the product link to track it.*\n\n"
                   "_Supported formats:_\n"
                   "🔗 Full: `https://www.amazon.com.eg/...`\n"
                   "⚡ Short: `https://amzn.eu/d/00rKyOJw`\n\n"
                   "_Just paste the link and I'll add it to your list!_")
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))

    elif action == "list":
        products = get_user_products(user_id)
        if not products:
            if lang == "ar":
                msg = "📦 *منتجاتك المتتبعة*\n\n_لم تضف أي منتجات بعد._\n\nاستخدم 📦 لإضافة أول منتج!"
            else:
                msg = "📦 *Your tracked products*\n\n_You haven't added any products yet._\n\nUse 📦 to add your first product!"
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
            return
        await query.edit_message_text(
            build_products_list_message(products, lang),
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=build_menu_markup(lang, user_id),
        )

    elif action == "check":
        from scheduler import check_prices

        if lang == "ar":
            checking = "🔍 *جاري فحص الأسعار...*\n\n_قد يستغرق هذا بعض الوقت._"
            done = "✅ *تم فحص الأسعار*\n\n_ستصلك رسالة عند تغيّر أي سعر._"
        else:
            checking = "🔍 *Checking prices...*\n\n_This can take a while._"
            done = "✅ *Price check complete*\n\n_You'll get a message for any price that changed._"

        await query.edit_message_text(checking, parse_mode="Markdown")
        await check_prices(context.bot, CHAT_ID)
        await query.edit_message_text(
            done, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id)
        )

    elif action == "untrack":
        context.user_data["awaiting_untrack_id"] = True
        context.user_data["awaiting_track_url"] = False
        if lang == "ar":
            msg = ("❌ *إزالة منتج من المراقبة*\n\n"
                   "_أرسل لي معرّف المنتج_ (استخدم 🧾 لرؤية قائمتك أولاً)\n"
                   "مثال: `1` أو `3`")
        else:
            msg = ("❌ *Remove a product from tracking*\n\n"
                   "_Send me the product ID_ (use 🧾 to see your list first)\n"
                   "Example: `1` or `3`")
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))

    elif action == "help":
        await query.edit_message_text(build_help_message(lang), parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))

    elif action == "language":
        back_btn = "◀ العودة" if lang == "ar" else "◀ Back"
        lang_keyboard = [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
                InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
            ],
            [InlineKeyboardButton(back_btn, callback_data="back_to_menu")],
        ]
        if lang == "ar":
            msg = "🌐 *اختر اللغة*\n\n_اختر لغتك المفضلة للروبوت:_"
        else:
            msg = "🌐 *Select Language*\n\n_Choose your preferred language for the bot:_"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(lang_keyboard))

    elif action.startswith("lang_"):
        new_lang = action.split("_")[1]
        context.user_data["language"] = new_lang
        set_user_language(user_id, new_lang)
        logger.info(f"[bot] User {user_id} changed language to {new_lang}")

        await query.edit_message_text(
            build_help_message(new_lang),
            parse_mode="Markdown",
            reply_markup=build_menu_markup(new_lang, user_id),
        )

    elif action == "back_to_menu":
        await query.edit_message_text(build_help_message(lang), parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))

    elif action == "admin_menu":
        if user_id != ADMIN_ID and not is_admin(user_id):
            await query.answer(adm(lang)["admin_only"], show_alert=True)
            return
        await show_admin_panel(query, lang)

    else:
        unknown_msg = "إجراء غير معروف" if lang == "ar" else "Unknown action"
        await query.edit_message_text(unknown_msg, reply_markup=build_menu_markup(lang, user_id))


async def process_track_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)

    if not url:
        if lang == "ar":
            msg = "❌ *رابط غير صالح*\n\nيرجى توفير رابط منتج أمازون صالح."
        else:
            msg = "❌ *Invalid URL*\n\nPlease provide a valid Amazon product link."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    if not is_valid_amazon_url(url):
        if lang == "ar":
            msg = ("❌ *ليس رابط أمازون*\n\n"
                   "_هذا لا يبدو أنه رابط أمازون._\n"
                   "تأكد من مشاركتك منتجًا من أمازون.")
        else:
            msg = ("❌ *Not an Amazon link*\n\n"
                   "_This doesn't look like an Amazon URL._\n"
                   "Please make sure you're sharing a product from Amazon.")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    if lang == "ar":
        waiting = "🔍 *جاري جلب بيانات المنتج...*\n\n_قد يستغرق هذا حتى دقيقة._"
    else:
        waiting = "🔍 *Getting the product info...*\n\n_This can take up to a minute._"
    status = await update.message.reply_text(waiting, parse_mode="Markdown")

    # fetch_product does blocking network I/O with retries and sleeps; running it
    # on the event loop would freeze the bot for every user until it finishes.
    result = await asyncio.to_thread(fetch_product, url, lang)

    if result is None:
        if lang == "ar":
            msg = ("⚠️ *تعذر جلب المنتج*\n\n"
                   "_قد يكون الرابط غير صالح، أو أمازون تحجب الطلب مؤقتًا._\n\n"
                   "💡 جرب:\n"
                   "• انسخ الرابط من شريط عنوان متصفحك\n"
                   "• انتظر قليلاً ثم حاول مرة أخرى\n"
                   "• تحقق من أن المنتج لا يزال موجودًا")
        else:
            msg = ("⚠️ *Could not fetch the product*\n\n"
                   "_The link might be invalid, or Amazon is temporarily blocking requests._\n\n"
                   "💡 Try:\n"
                   "• Copy the link from your browser address bar\n"
                   "• Wait a moment and try again\n"
                   "• Check the product still exists")
        await status.edit_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    product_id = add_product(url, result["name"], result["price"], result.get("image"))
    add_user_product(user_id, product_id)

    await status.edit_text(
        build_tracking_success_message(result["name"], result["price"], lang),
        parse_mode="Markdown",
    )


async def process_untrack_id(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id_text: str):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)

    if not product_id_text.isdigit():
        if lang == "ar":
            msg = "❌ *معرّف غير صالح*\n\n_يرجى إرسال رقم المنتج فقط (مثل `1` أو `2`)_"
        else:
            msg = "❌ *Invalid ID*\n\n_Please send just the product number (e.g., `1` or `2`)_"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    product_id = int(product_id_text)
    product = get_product_by_id(product_id)
    if product is None:
        if lang == "ar":
            msg = f"❌ *المنتج غير موجود*\n\n_لا يوجد منتج برقم {product_id}._\n\nاستخدم 🧾 لفحص قائمتك."
        else:
            msg = f"❌ *Product not found*\n\n_No product with ID {product_id}._\n\nUse 🧾 to check your list."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    remove_user_product(user_id, product_id)
    product_name = product[2]
    if lang == "ar":
        msg = f"✅ تم إزالة {product_name}"
    else:
        msg = f"✅ Removed: {product_name}"
    await update.message.reply_text(msg)


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    if not context.args:
        if lang == "ar":
            msg = "📦 *الاستخدام: /track* `<رابط-أمازون>`\n\nمثال:\n`/track https://amzn.eu/d/00rKyOJw`"
        else:
            msg = "📦 *Usage: /track* `<amazon-url>`\n\nExample:\n`/track https://amzn.eu/d/00rKyOJw`"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    await process_track_url(update, context, context.args[0].strip())


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    products = get_user_products(user_id)
    if not products:
        if lang == "ar":
            msg = ("📦 *لا توجد منتجات مراقبة حتى الآن*\n\n"
                   "_ابدأ بتتبع المنتجات لرؤيتها هنا._\n"
                   "استخدم 📦 أو `/track <رابط>` لإضافة واحد!")
        else:
            msg = ("📦 *No products tracked yet*\n\n"
                   "_Start tracking products to see them here._\n"
                   "Use 📦 or `/track <url>` to add one!")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    await update.message.reply_text(
        build_products_list_message(products, lang),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=build_menu_markup(lang, user_id),
    )


async def untrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    if not context.args:
        if lang == "ar":
            msg = ("🗑 *الاستخدام: /untrack* `<معرف-المنتج>`\n\n"
                   "مثال:\n"
                   "`/untrack 1`\n\n"
                   "_استخدم /list لرؤية معرفات منتجاتك_")
        else:
            msg = ("🗑 *Usage: /untrack* `<product-id>`\n\n"
                   "Example:\n"
                   "`/untrack 1`\n\n"
                   "_Use /list to see your product IDs_")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    await process_untrack_id(update, context, context.args[0].strip())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)

    t = adm(lang)
    back = [[InlineKeyboardButton(t["back_admin"], callback_data="admin_menu")]]

    if context.user_data.get("awaiting_authorize_name"):
        username = update.message.text.strip()
        context.user_data["authorize_username"] = username
        context.user_data["awaiting_authorize_name"] = False
        context.user_data["awaiting_authorize_id"] = True

        await update.message.reply_text(
            t["step2"].format(name=username),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back),
        )
        return

    if context.user_data.get("awaiting_authorize_id"):
        if update.message.text.strip().isdigit():
            target_id = int(update.message.text.strip())
            username = context.user_data.pop("authorize_username", "User")
            context.user_data["awaiting_authorize_id"] = False

            add_authorized_user(target_id, username)
            await update.message.reply_text(
                t["authorized"].format(name=username, uid=target_id),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(back),
            )
        else:
            await update.message.reply_text(t["invalid_id"], reply_markup=InlineKeyboardMarkup(back))
        return

    if context.user_data.get("awaiting_revoke_id"):
        context.user_data["awaiting_revoke_id"] = False
        if update.message.text.strip().isdigit():
            target_id = int(update.message.text.strip())
            remove_authorized_user(target_id)
            await update.message.reply_text(
                f"{t['revoked']}: {target_id}", reply_markup=InlineKeyboardMarkup(back)
            )
        else:
            await update.message.reply_text(t["invalid_id"], reply_markup=InlineKeyboardMarkup(back))
        return

    if not is_authorized(update):
        user_id = update.effective_user.id
        keyboard = [
            [InlineKeyboardButton("📋 Copy User ID", callback_data="copy_user_id")],
            [InlineKeyboardButton("❓ Get Instructions", callback_data="get_instructions")],
        ]

        msg = (
            f"🚫 *Not Authorized*\n\n"
            f"Your User ID: `{user_id}`\n\n"
            f"Please contact the admin to request access.\n"
            f"Send them your User ID and desired display name."
        )
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if context.user_data.get("awaiting_track_url"):
        context.user_data["awaiting_track_url"] = False
        await process_track_url(update, context, update.message.text.strip())
        return

    if context.user_data.get("awaiting_untrack_id"):
        context.user_data["awaiting_untrack_id"] = False
        await process_untrack_id(update, context, update.message.text.strip())
        return

    text_lower = update.message.text.lower() if update.message.text else ""
    if text_lower in {"menu", "main menu", "show menu", "start"}:
        await update.message.reply_text(build_help_message(lang), parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))
        return

    if lang == "ar":
        msg = "👋 *استخدم القائمة أدناه للبدء!*\n\n_الأوامر:_ `/track`, `/list`, `/check`, `/untrack`"
    else:
        msg = "👋 *Use the menu below to get started!*\n\n_Commands:_ `/track`, `/list`, `/check`, `/untrack`"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))


ADMIN_STRINGS = {
    "en": {
        "panel": "⚙️ *Admin Panel*",
        "btn_users": "👥 Users",
        "btn_stats": "📊 Stats",
        "btn_authorize": "➕ Authorize User",
        "btn_revoke": "➖ Revoke User",
        "back": "◀ Back",
        "back_admin": "◀ Back to Admin",
        "admin_only": "🚫 Admin only",
        "users_title": "👥 *Authorized Users*",
        "no_users": "No users authorized yet.",
        "badge_admin": "🔐 Admin",
        "badge_user": "✅ User",
        "name": "Name",
        "stats_title": "📊 *Bot Statistics*",
        "stats_users": "👥 Authorized Users",
        "stats_products": "📦 Total Products",
        "stats_interval": "⏱️ Check Interval",
        "minutes": "minutes",
        "stats_db": "🗄️ Database",
        "stats_db_ok": "Active",
        "stats_sched": "🔄 Scheduler",
        "stats_sched_ok": "Running",
        "no_revoke": "❌ No users to revoke",
        "select_revoke": "Select user to revoke:",
        "revoked": "✅ Revoked",
        "authorize_prompt": "📝 *Authorize New User*\n\nEnter display name:",
        "step2": "📝 *Step 2*\n\nEnter {name}'s Telegram ID:",
        "authorized": "✅ *{name}* authorized! ({uid})",
        "invalid_id": "❌ Invalid ID. Please enter numbers only.",
    },
    "ar": {
        "panel": "⚙️ *لوحة الإدارة*",
        "btn_users": "👥 المستخدمون",
        "btn_stats": "📊 الإحصائيات",
        "btn_authorize": "➕ تفويض مستخدم",
        "btn_revoke": "➖ إزالة مستخدم",
        "back": "◀ رجوع",
        "back_admin": "◀ رجوع للإدارة",
        "admin_only": "🚫 للمشرفين فقط",
        "users_title": "👥 *المستخدمون المصرح لهم*",
        "no_users": "لا يوجد مستخدمون حتى الآن.",
        "badge_admin": "🔐 مشرف",
        "badge_user": "✅ مستخدم",
        "name": "الاسم",
        "stats_title": "📊 *إحصائيات البوت*",
        "stats_users": "👥 المستخدمون المصرح لهم",
        "stats_products": "📦 إجمالي المنتجات",
        "stats_interval": "⏱️ فترة الفحص",
        "minutes": "دقيقة",
        "stats_db": "🗄️ قاعدة البيانات",
        "stats_db_ok": "نشطة",
        "stats_sched": "🔄 المجدول",
        "stats_sched_ok": "يعمل",
        "no_revoke": "❌ لا يوجد مستخدمون لإزالتهم",
        "select_revoke": "اختر المستخدم للإزالة:",
        "revoked": "✅ تم إزالة",
        "authorize_prompt": "📝 *تفويض مستخدم جديد*\n\nأدخل اسم المستخدم:",
        "step2": "📝 *خطوة 2*\n\nأدخل معرف {name}:",
        "authorized": "✅ تم تفويض *{name}*! ({uid})",
        "invalid_id": "❌ معرف غير صالح. أرقام فقط.",
    },
}


def adm(lang: str) -> dict:
    """Admin panel strings for the given language, falling back to English."""
    return ADMIN_STRINGS.get(lang, ADMIN_STRINGS["en"])


def build_users_message(users, lang: str) -> str:
    """Render the authorized-user list in the admin's language."""
    t = adm(lang)
    if not users:
        return f"{t['users_title']}\n\n{t['no_users']}"

    lines = [f"{t['users_title']} ({len(users)})\n"]
    for uid, username, is_admin_flag, _auth_date in users:
        badge = t["badge_admin"] if is_admin_flag else t["badge_user"]
        lines.append(f"\n{badge}\n`{uid}`\n{t['name']}: {username}")
    return "\n".join(lines)


def build_stats_message(users, products, lang: str) -> str:
    """Render bot statistics in the admin's language."""
    t = adm(lang)
    return (
        f"{t['stats_title']}\n\n"
        f"{t['stats_users']}: {len(users)}\n"
        f"{t['stats_products']}: {len(products)}\n"
        f"{t['stats_interval']}: {INTERVAL} {t['minutes']}\n"
        f"{t['stats_db']}: {t['stats_db_ok']}\n"
        f"{t['stats_sched']}: {t['stats_sched_ok']}"
    )


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    t = adm(lang)
    if user_id != ADMIN_ID and not is_admin(user_id):
        await update.message.reply_text(t["admin_only"])
        return

    keyboard = [[InlineKeyboardButton(t["back_admin"], callback_data="admin_menu")]]
    await update.message.reply_text(
        build_users_message(get_authorized_users(), lang),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    t = adm(lang)
    if user_id != ADMIN_ID and not is_admin(user_id):
        await update.message.reply_text(t["admin_only"])
        return

    keyboard = [[InlineKeyboardButton(t["back_admin"], callback_data="admin_menu")]]
    await update.message.reply_text(
        build_stats_message(get_authorized_users(), get_all_products(), lang),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    from scheduler import check_prices

    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    if lang == "ar":
        checking = "🔍 *جاري فحص الأسعار...*\n\n_قد يستغرق هذا بعض الوقت._"
        done = "✅ *تم فحص الأسعار*\n\n_ستصلك رسالة عند تغيّر أي سعر._"
    else:
        checking = "🔍 *Checking prices...*\n\n_This can take a while._"
        done = "✅ *Price check complete*\n\n_You'll get a message for any price that changed._"

    status = await update.message.reply_text(checking, parse_mode="Markdown")
    await check_prices(context.bot, CHAT_ID)
    await status.edit_text(done, parse_mode="Markdown", reply_markup=build_menu_markup(lang, user_id))


async def show_admin_panel(update_or_query, lang: str = "en"):
    t = adm(lang)
    keyboard = [
        [InlineKeyboardButton(t["btn_users"], callback_data="admin_users"),
         InlineKeyboardButton(t["btn_stats"], callback_data="admin_stats")],
        [InlineKeyboardButton(t["btn_authorize"], callback_data="admin_authorize"),
         InlineKeyboardButton(t["btn_revoke"], callback_data="admin_revoke")],
        [InlineKeyboardButton(t["back"], callback_data="back_to_menu")],
    ]

    msg = t["panel"]

    if hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update_or_query.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    if user_id != ADMIN_ID and not is_admin(user_id):
        await update.message.reply_text(adm(lang)["admin_only"])
        return

    await show_admin_panel(update, lang)


async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(context, user_id)
    t = adm(lang)

    if user_id != ADMIN_ID and not is_admin(user_id):
        await update.callback_query.answer(t["admin_only"], show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    action = query.data
    back = [[InlineKeyboardButton(t["back_admin"], callback_data="admin_menu")]]

    if action == "admin_users":
        await query.edit_message_text(
            build_users_message(get_authorized_users(), lang),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back),
        )

    elif action == "admin_stats":
        await query.edit_message_text(
            build_stats_message(get_authorized_users(), get_all_products(), lang),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back),
        )

    elif action == "admin_authorize":
        context.user_data["awaiting_authorize_name"] = True
        await query.edit_message_text(
            t["authorize_prompt"], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(back)
        )

    elif action == "admin_revoke":
        revocable = [(uid, name) for uid, name, is_admin_flag, _ in get_authorized_users() if not is_admin_flag]
        if not revocable:
            await query.edit_message_text(t["no_revoke"], reply_markup=InlineKeyboardMarkup(back))
            return

        keyboard = [
            [InlineKeyboardButton(f"❌ {name}", callback_data=f"revoke_{uid}")]
            for uid, name in revocable
        ]
        keyboard.append([InlineKeyboardButton(t["back"], callback_data="admin_menu")])
        await query.edit_message_text(t["select_revoke"], reply_markup=InlineKeyboardMarkup(keyboard))

    elif action.startswith("revoke_"):
        target_id = int(action.split("_")[1])
        user_to_revoke = next(
            (name for uid, name, _, _ in get_authorized_users() if uid == target_id), None
        )

        if user_to_revoke:
            remove_authorized_user(target_id)
            await query.edit_message_text(
                f"{t['revoked']}: {user_to_revoke}", reply_markup=InlineKeyboardMarkup(back)
            )
        else:
            await show_admin_panel(query, lang)


async def post_init(application):
    add_authorized_user(ADMIN_ID, "Admin", True)
    start_scheduler(application.bot, CHAT_ID, INTERVAL)


def main():
    validate_config()
    init_db()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("untrack", untrack))
    app.add_handler(CommandHandler("check", check_now))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("stats", admin_stats))

    app.add_handler(CallbackQueryHandler(handle_unauthorized_request, pattern="^(copy_user_id|get_instructions)$"))
    app.add_handler(CallbackQueryHandler(handle_menu_button, pattern="^(track|list|check|untrack|help|language|lang_(en|ar)|back_to_menu|admin_menu)$"))
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(admin_|revoke_)"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
