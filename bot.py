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
    init_db, add_product, get_all_products, remove_product, get_product_by_id,
    is_user_authorized, is_admin, add_authorized_user, remove_authorized_user,
    get_authorized_users, get_user_language, set_user_language
)
from scraper import fetch_product
from scheduler import start_scheduler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ADMIN_ID = int(CHAT_ID) if CHAT_ID else None
INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))


def is_user_auth(user_id: int) -> bool:
    """Check if user is authorized."""
    return user_id == ADMIN_ID or is_user_authorized(user_id)


def is_user_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id == ADMIN_ID or is_admin(user_id)

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


def build_menu_markup(lang: str = "en") -> InlineKeyboardMarkup:
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

    for pid, url, name, last_price, prev_price, image_url, added_at in products:
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
    """Only allow messages from the configured chat ID."""
    return str(update.effective_chat.id) == str(CHAT_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if "language" not in context.user_data:
        context.user_data["language"] = get_user_language(user_id)
    context.user_data["awaiting_track_url"] = False
    context.user_data["awaiting_untrack_id"] = False
    lang = context.user_data["language"]
    await update.message.reply_text(
        build_help_message(lang),
        parse_mode="Markdown",
        reply_markup=build_menu_markup(lang)
    )


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
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
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))

    elif action == "list":
        products = get_all_products()
        if not products:
            if lang == "ar":
                msg = "📦 *منتجاتك المتتبعة*\n\n_لم تضف أي منتجات بعد._\n\nاستخدم 📦 لإضافة أول منتج!"
            else:
                msg = "📦 *Your tracked products*\n\n_You haven't added any products yet._\n\nUse 📦 to add your first product!"
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
            return
        await query.edit_message_text(
            build_products_list_message(products, lang),
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=build_menu_markup(lang),
        )

    elif action == "check":
        if lang == "ar":
            check_msg = "🔍 *جاري فحص الأسعار...*\n_جاري تحديث الأسعار من أمازون._"
            done_msg = "✅ *تم تحديث جميع الأسعار!*\n\n_اعرض قائمتك لرؤية أحدث الأسعار._"
        else:
            check_msg = "🔍 *Checking all prices...*\n_Updating latest prices from Amazon._"
            done_msg = "✅ *All prices updated!*\n\n_View your list to see the latest prices._"
        await query.edit_message_text(check_msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        from scheduler import check_prices
        await check_prices(context.bot, CHAT_ID)
        await query.edit_message_text(done_msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))

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
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))

    elif action == "help":
        await query.edit_message_text(build_help_message(lang), parse_mode="Markdown", reply_markup=build_menu_markup(lang))

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
        set_user_language(user_id, new_lang)  # Save to database
        update_msg = "✅ *Language Updated*" if new_lang == "en" else "✅ *تم تحديث اللغة*"
        await query.edit_message_text(update_msg, parse_mode="Markdown", reply_markup=build_menu_markup(new_lang))

    elif action == "back_to_menu":
        await query.edit_message_text(build_help_message(lang), parse_mode="Markdown", reply_markup=build_menu_markup(lang))

    else:
        unknown_msg = "إجراء غير معروف" if lang == "ar" else "Unknown action"
        await query.edit_message_text(unknown_msg, reply_markup=build_menu_markup(lang))


async def process_track_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    lang = context.user_data.get("language", "en")

    if not url:
        if lang == "ar":
            msg = "❌ *رابط غير صالح*\n\nيرجى توفير رابط منتج أمازون صالح."
        else:
            msg = "❌ *Invalid URL*\n\nPlease provide a valid Amazon product link."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
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
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    if lang == "ar":
        wait_msg = "🔍 جاري جلب تفاصيل المنتج...\n_يرجى الانتظار..._"
    else:
        wait_msg = "🔍 Fetching product details...\n_Please wait..._"
    await update.message.reply_text(wait_msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))

    result = fetch_product(url, lang)
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
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    add_product(url, result["name"], result["price"], result.get("image"))
    await update.message.reply_text(
        build_tracking_success_message(result["name"], result["price"], lang),
        parse_mode="Markdown",
        reply_markup=build_menu_markup(lang),
    )


async def process_untrack_id(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id_text: str):
    lang = context.user_data.get("language", "en")

    if not product_id_text.isdigit():
        if lang == "ar":
            msg = "❌ *معرّف غير صالح*\n\n_يرجى إرسال رقم المنتج فقط (مثل `1` أو `2`)_"
        else:
            msg = "❌ *Invalid ID*\n\n_Please send just the product number (e.g., `1` or `2`)_"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    product_id = int(product_id_text)
    product = get_product_by_id(product_id)
    if product is None:
        if lang == "ar":
            msg = f"❌ *المنتج غير موجود*\n\n_لا يوجد منتج برقم {product_id}._\n\nاستخدم 🧾 لفحص قائمتك."
        else:
            msg = f"❌ *Product not found*\n\n_No product with ID {product_id}._\n\nUse 🧾 to check your list."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    remove_product(product_id)
    product_name = product[2]
    if lang == "ar":
        msg = f"✅ *تمت الإزالة من المراقبة*\n\n_لم يعد قيد المراقبة:_\n📦 {product_name}"
    else:
        msg = f"✅ *Removed from tracking*\n\n_No longer monitoring:_\n📦 {product_name}"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    lang = context.user_data.get("language", "en")
    if not context.args:
        if lang == "ar":
            msg = "📦 *الاستخدام: /track* `<رابط-أمازون>`\n\nمثال:\n`/track https://amzn.eu/d/00rKyOJw`"
        else:
            msg = "📦 *Usage: /track* `<amazon-url>`\n\nExample:\n`/track https://amzn.eu/d/00rKyOJw`"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    await process_track_url(update, context, context.args[0].strip())


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    lang = context.user_data.get("language", "en")
    products = get_all_products()
    if not products:
        if lang == "ar":
            msg = ("📦 *لا توجد منتجات مراقبة حتى الآن*\n\n"
                   "_ابدأ بتتبع المنتجات لرؤيتها هنا._\n"
                   "استخدم 📦 أو `/track <رابط>` لإضافة واحد!")
        else:
            msg = ("📦 *No products tracked yet*\n\n"
                   "_Start tracking products to see them here._\n"
                   "Use 📦 or `/track <url>` to add one!")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    await update.message.reply_text(
        build_products_list_message(products, lang),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=build_menu_markup(lang),
    )


async def untrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    lang = context.user_data.get("language", "en")
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
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    await process_untrack_id(update, context, context.args[0].strip())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    lang = context.user_data.get("language", "en")

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
        await update.message.reply_text(build_help_message(lang), parse_mode="Markdown", reply_markup=build_menu_markup(lang))
        return

    if lang == "ar":
        msg = "👋 *استخدم القائمة أدناه للبدء!*\n\n_الأوامر:_ `/track`, `/list`, `/check`, `/untrack`"
    else:
        msg = "👋 *Use the menu below to get started!*\n\n_Commands:_ `/track`, `/list`, `/check`, `/untrack`"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))


async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    lang = context.user_data.get("language", "en")
    if lang == "ar":
        check_msg = "🔍 *جاري فحص الأسعار...*\n_يرجى الانتظار أثناء تحديث جميع الأسعار._"
        done_msg = "✅ *فحص الأسعار مكتمل!*\n\n_تحقق من القائمة لرؤية أحدث الأسعار._"
    else:
        check_msg = "🔍 *Checking prices...*\n_Please wait while I update all prices._"
        done_msg = "✅ *Price check complete!*\n\n_Check the list to see the latest prices._"

    await update.message.reply_text(check_msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))
    from scheduler import check_prices
    await check_prices(context.bot, CHAT_ID)
    await update.message.reply_text(done_msg, parse_mode="Markdown", reply_markup=build_menu_markup(lang))


async def post_init(application):
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
    app.add_handler(CallbackQueryHandler(handle_menu_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
