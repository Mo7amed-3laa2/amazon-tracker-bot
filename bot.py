import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
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


def is_authorized(update: Update) -> bool:
    """Only allow messages from the configured chat ID."""
    return str(update.effective_chat.id) == str(CHAT_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "Amazon Egypt Price Tracker Bot\n\n"
        "Commands:\n"
        "/track <url> — Track a product\n"
        "/list — Show all tracked products\n"
        "/untrack <id> — Stop tracking a product\n"
        "/check — Run a price check now"
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /track <amazon product url>")
        return

    url = context.args[0].strip()

    if "amazon.com.eg" not in url and "amazon." not in url:
        await update.message.reply_text("Please provide a valid Amazon product URL.")
        return

    await update.message.reply_text("Fetching product info, please wait...")

    result = fetch_product(url)
    if result is None:
        await update.message.reply_text(
            "Could not fetch the product. Please check the URL or try again later.\n"
            "Amazon may be blocking the request temporarily."
        )
        return

    add_product(url, result["name"], result["price"])
    await update.message.reply_text(
        f"Tracking started!\n\n"
        f"*{result['name']}*\n"
        f"Current price: `EGP {result['price']:,.2f}`",
        parse_mode="Markdown",
    )


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    products = get_all_products()
    if not products:
        await update.message.reply_text("No products tracked yet. Use /track <url> to add one.")
        return

    lines = ["*Tracked Products:*\n"]
    for pid, url, name, price in products:
        price_str = f"EGP {price:,.2f}" if price is not None else "N/A"
        lines.append(f"*{pid}.* {name}\nPrice: `{price_str}`\n[Link]({url})\n")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def untrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /untrack <product id>\nUse /list to see product IDs.")
        return

    product_id = int(context.args[0])
    product = get_product_by_id(product_id)
    if product is None:
        await update.message.reply_text(f"No product found with ID {product_id}.")
        return

    remove_product(product_id)
    await update.message.reply_text(f"Stopped tracking: *{product[2]}*", parse_mode="Markdown")


async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("Running price check now...")
    from scheduler import check_prices
    await check_prices(context.bot, CHAT_ID)
    await update.message.reply_text("Price check complete.")


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

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
