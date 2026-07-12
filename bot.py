import logging
import os
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
        "🤖 Amazon Egypt Price Tracker Bot\n\n"
        "Use the buttons below to manage your tracker.\n"
        "You can still use commands, but the menu is the main experience."
    )


def build_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📦 Track Product", callback_data="track"),
            InlineKeyboardButton("🧾 Show List", callback_data="list"),
        ],
        [
            InlineKeyboardButton("🔎 Check Price", callback_data="check"),
            InlineKeyboardButton("🗑 Untrack", callback_data="untrack"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_tracking_success_message(product_name: str, price: float) -> str:
    return (
        f"✅ Tracking started!\n\n"
        f"*{product_name}*\n"
        f"Current price: `EGP {price:,.2f}`\n\n"
        f"You can see it anytime with /list"
    )


def build_products_list_message(products) -> str:
    lines = ["📦 *Tracked Products:*\n"]
    for pid, url, name, price in products:
        price_str = f"EGP {price:,.2f}" if price is not None else "N/A"
        lines.append(f"*{pid}.* {name}\nPrice: `{price_str}`\n[Link]({url})\n")
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
            "Send me the Amazon product URL to track it.\nExamples:\n• https://www.amazon.com.eg/...\n• https://amzn.eu/d/00rKyOJw",
            reply_markup=build_menu_markup(),
        )
    elif action == "list":
        products = get_all_products()
        if not products:
            await query.edit_message_text(
                "No products tracked yet. Use the menu to add one by sending a product URL.",
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
        await query.edit_message_text("Running price check now...", reply_markup=build_menu_markup())
        from scheduler import check_prices
        await check_prices(context.bot, CHAT_ID)
        await query.edit_message_text("Price check complete.", reply_markup=build_menu_markup())
    elif action == "untrack":
        context.user_data["awaiting_untrack_id"] = True
        context.user_data["awaiting_track_url"] = False
        await query.edit_message_text(
            "Send me the product ID to remove from tracking.\nUse the list view to see the IDs.",
            reply_markup=build_menu_markup(),
        )
    elif action == "help":
        await query.edit_message_text(build_help_message(), reply_markup=build_menu_markup())
    else:
        await query.edit_message_text("Unknown action", reply_markup=build_menu_markup())


async def process_track_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    if not url:
        await update.message.reply_text("Please provide a valid Amazon product URL.", reply_markup=build_menu_markup())
        return

    if not is_valid_amazon_url(url):
        await update.message.reply_text("Please provide a valid Amazon product URL.", reply_markup=build_menu_markup())
        return

    await update.message.reply_text("🔎 Fetching product info, please wait...", reply_markup=build_menu_markup())

    result = fetch_product(url)
    if result is None:
        await update.message.reply_text(
            "Could not fetch the product. Please check the URL or try again later.\n"
            "Amazon may be blocking the request temporarily.",
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
            "Please send a valid product ID.",
            reply_markup=build_menu_markup(),
        )
        return

    product_id = int(product_id_text)
    product = get_product_by_id(product_id)
    if product is None:
        await update.message.reply_text(f"No product found with ID {product_id}.", reply_markup=build_menu_markup())
        return

    remove_product(product_id)
    await update.message.reply_text(
        f"🗑️ Stopped tracking: *{product[2]}*",
        parse_mode="Markdown",
        reply_markup=build_menu_markup(),
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /track <amazon product url>",
            reply_markup=build_menu_markup(),
        )
        return

    await process_track_url(update, context, context.args[0].strip())


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    products = get_all_products()
    if not products:
        await update.message.reply_text("No products tracked yet. Use /track <url> to add one.")
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
            "Usage: /untrack <product id>\nUse /list to see product IDs.",
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

    if update.message.text and update.message.text.lower() in {"menu", "main menu", "show menu"}:
        await update.message.reply_text(build_help_message(), reply_markup=build_menu_markup())
        return

    await update.message.reply_text(build_help_message(), reply_markup=build_menu_markup())


async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("Running price check now...", reply_markup=build_menu_markup())
    from scheduler import check_prices
    await check_prices(context.bot, CHAT_ID)
    await update.message.reply_text("Price check complete.", reply_markup=build_menu_markup())


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
