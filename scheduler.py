import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from database import get_all_products, update_price
from scraper import fetch_product

logger = logging.getLogger(__name__)


async def check_prices(bot: Bot, chat_id: str):
    products = get_all_products()
    if not products:
        return

    logger.info(f"[scheduler] Checking {len(products)} product(s)...")

    for product_id, url, name, last_price in products:
        result = fetch_product(url)
        if result is None:
            logger.warning(f"[scheduler] Could not fetch: {url}")
            continue

        new_price = result["price"]
        product_name = result["name"]

        if last_price is None:
            update_price(url, new_price)
            continue

        if new_price != last_price:
            direction = "dropped" if new_price < last_price else "increased"
            emoji = "" if new_price < last_price else ""
            message = (
                f"{emoji} *Price {direction}!*\n\n"
                f"*{product_name}*\n"
                f"Old price: `EGP {last_price:,.2f}`\n"
                f"New price: `EGP {new_price:,.2f}`\n\n"
                f"[View on Amazon]({url})"
            )
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=False,
            )
            update_price(url, new_price)
            logger.info(f"[scheduler] Price changed for '{product_name}': {last_price} → {new_price}")
        else:
            logger.info(f"[scheduler] No change for '{product_name}': EGP {new_price:,.2f}")


def start_scheduler(bot: Bot, chat_id: str, interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_prices,
        trigger="interval",
        minutes=interval_minutes,
        args=[bot, chat_id],
        id="price_check",
    )
    scheduler.start()
    logger.info(f"[scheduler] Started — checking every {interval_minutes} minute(s).")
    return scheduler
