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
from database import init_db, add_product, get_all_products, remove_product, get_product_by_id
from scraper import fetch_product
from scheduler import start_scheduler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))


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


def build_help_message() -> str:
    return (
        "🤖 *Amazon Price Tracker*\n\n"
        "Track product prices and get automatic updates!\n\n"
        "_Commands available:_\n"
        "• 📦 `/track <url>` - Add a product\n"
        "• 🧾 `/list` - Show tracked products\n"
        "• 🔎 `/check` - Check prices now\n"
        "• 🗑 `/untrack <id>` - Remove a product\n\n"
        "_Supported link formats:_\n"
        "• Full: `https://www.amazon.com.eg/...`\n"
        "• Shortened: `https://amzn.eu/d/...`"
    )


def build_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📦 Add Product", callback_data="track"),
            InlineKeyboardButton("🧾 My Products", callback_data="list"),
        ],
        [
            InlineKeyboardButton("🔎 Check Now", callback_data="check"),
            InlineKeyboardButton("❌ Remove", callback_data="untrack"),
        ],
        [
            InlineKeyboardButton("❓ Help & Info", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_tracking_success_message(product_name: str, price: float) -> str:
    return (
        f"✅ *Successfully Added!*\n\n"
        f"📦 *{product_name}*\n"
        f"💰 Current Price: `EGP {price:,.2f}`\n\n"
        f"_You'll receive updates when the price changes._\n"
        f"Check your list anytime with 🧾 or `/list`"
    )


def build_products_list_message(products) -> str:
    if not products:
        return "📦 *Tracked Products:*\n\nNo products tracked yet."

    lines = [f"📦 *Tracked Products* ({len(products)})\n"]
    for pid, url, name, price, added_at in products:
        price_str = f"EGP {price:,.2f}" if price is not None else "N/A"
        added_date = datetime.fromisoformat(added_at).strftime("%b %d") if added_at else "N/A"
        lines.append(
            f"*{pid}.* {name}\n"
            f"💰 Price: `{price_str}`\n"
            f"📅 Added: {added_date}\n"
            f"🔗 [View on Amazon]({url})\n"
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
        "amzn.",
    ]
    return any(domain in url for domain in amazon_domains)


def is_authorized(update: Update) -> bool:
    """Only allow messages from the configured chat ID."""
    return str(update.effective_chat.id) == str(CHAT_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    context.user_data["awaiting_track_url"] = False
    context.user_data["awaiting_untrack_id"] = False
    await update.message.reply_text(build_help_message(), reply_markup=build_menu_markup())


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    query = update.callback_query
    await query.answer()

    action = query.data
    if action == "track":
        context.user_data["awaiting_track_url"] = True
        context.user_data["awaiting_untrack_id"] = False
        await query.edit_message_text(
            "📤 *Send me the product link to track it.*\n\n"
            "_Supported formats:_\n"
            "🔗 Full: `https://www.amazon.com.eg/...`\n"
            "⚡ Short: `https://amzn.eu/d/00rKyOJw`\n\n"
            "_Just paste the link and I'll add it to your list!_",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
    elif action == "list":
        products = get_all_products()
        if not products:
            await query.edit_message_text(
                "📦 *Your tracked products*\n\n_You haven't added any products yet._\n\n"
                "Use 📦 to add your first product!",
                parse_mode="Markdown",
                reply_markup=build_menu_markup(),
            )
            return
        await query.edit_message_text(
            build_products_list_message(products),
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=build_menu_markup(),
        )
    elif action == "check":
        await query.edit_message_text(
            "🔍 *Checking all prices...*\n_Updating latest prices from Amazon._",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        from scheduler import check_prices
        await check_prices(context.bot, CHAT_ID)
        await query.edit_message_text(
            "✅ *All prices updated!*\n\n_View your list to see the latest prices._",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
    elif action == "untrack":
        context.user_data["awaiting_untrack_id"] = True
        context.user_data["awaiting_track_url"] = False
        await query.edit_message_text(
            "❌ *Remove a product from tracking*\n\n"
            "_Send me the product ID_ (use 🧾 to see your list first)\n"
            "Example: `1` or `3`",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
    elif action == "help":
        await query.edit_message_text(build_help_message(), reply_markup=build_menu_markup())
    else:
        await query.edit_message_text("Unknown action", reply_markup=build_menu_markup())


async def process_track_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    if not url:
        await update.message.reply_text(
            "❌ *Invalid URL*\n\nPlease provide a valid Amazon product link.",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    if not is_valid_amazon_url(url):
        await update.message.reply_text(
            "❌ *Not an Amazon link*\n\n"
            "_This doesn't look like an Amazon URL._\n"
            "Please make sure you're sharing a product from Amazon.",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    await update.message.reply_text(
        "🔍 Fetching product details...\n_Please wait..._",
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )

    result = fetch_product(url)
    if result is None:
        await update.message.reply_text(
            "⚠️ *Could not fetch the product*\n\n"
            "_The link might be invalid, or Amazon is temporarily blocking requests._\n\n"
            "💡 Try:\n"
            "• Copy the link from your browser address bar\n"
            "• Wait a moment and try again\n"
            "• Check the product still exists",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    add_product(url, result["name"], result["price"])
    await update.message.reply_text(
        build_tracking_success_message(result["name"], result["price"]),
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )


async def process_untrack_id(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id_text: str):
    if not product_id_text.isdigit():
        await update.message.reply_text(
            "❌ *Invalid ID*\n\n_Please send just the product number (e.g., `1` or `2`)_",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    product_id = int(product_id_text)
    product = get_product_by_id(product_id)
    if product is None:
        await update.message.reply_text(
            f"❌ *Product not found*\n\n_No product with ID {product_id}._\n\nUse 🧾 to check your list.",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    remove_product(product_id)
    product_name = product[2]
    await update.message.reply_text(
        f"✅ *Removed from tracking*\n\n"
        f"_No longer monitoring:_\n"
        f"📦 {product_name}",
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text(
            "📦 *Usage: /track* `<amazon-url>`\n\n"
            "Example:\n"
            "`/track https://amzn.eu/d/00rKyOJw`",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    await process_track_url(update, context, context.args[0].strip())


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    products = get_all_products()
    if not products:
        await update.message.reply_text(
            "📦 *No products tracked yet*\n\n"
            "_Start tracking products to see them here._\n"
            "Use 📦 or `/track <url>` to add one!",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    await update.message.reply_text(
        build_products_list_message(products),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=build_menu_markup(),
    )


async def untrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text(
            "🗑 *Usage: /untrack* `<product-id>`\n\n"
            "Example:\n"
            "`/untrack 1`\n\n"
            "_Use /list to see your product IDs_",
            parse_mode="Markdown",
            reply_markup=build_menu_markup(),
        )
        return

    await process_untrack_id(update, context, context.args[0].strip())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
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
        await update.message.reply_text(build_help_message(), parse_mode="Markdown", reply_markup=build_menu_markup())
        return

    await update.message.reply_text(
        "👋 *Use the menu below to get started!*\n\n_Commands:_ `/track`, `/list`, `/check`, `/untrack`",
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )


async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🔍 *Checking prices...*\n_Please wait while I update all prices._",
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )
    from scheduler import check_prices
    await check_prices(context.bot, CHAT_ID)
    await update.message.reply_text(
        "✅ *Price check complete!*\n\n_Check the list to see the latest prices._",
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )


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
