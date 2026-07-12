import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from database import get_all_products, update_price, get_all_authorized_users_for_notification
from scraper import fetch_product

logger = logging.getLogger(__name__)


def get_localized_notification(product_name: str, last_price: float, new_price: float, url: str, lang: str) -> str:
    """Format a price change notification in the specified language."""
    price_diff = last_price - new_price
    price_percent = (price_diff / last_price) * 100

    if lang == "ar":
        if new_price < last_price:
            emoji = "📉"
            direction = "السعر انخفض"
            change_text = f"💚 *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"
        else:
            emoji = "📈"
            direction = "السعر ارتفع"
            change_text = f"❤️ *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"

        message = (
            f"{emoji} *{direction}!*\n\n"
            f"📦 *{product_name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"السعر السابق: ~~`EGP {last_price:,.2f}`~~\n"
            f"السعر الحالي: `EGP {new_price:,.2f}`\n"
            f"التغير: {change_text}\n\n"
            f"🔗 [عرض على أمازون]({url})"
        )
    else:
        if new_price < last_price:
            emoji = "📉"
            direction = "dropped"
            change_text = f"💚 *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"
        else:
            emoji = "📈"
            direction = "increased"
            change_text = f"❤️ *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"

        message = (
            f"{emoji} *Price {direction}!*\n\n"
            f"📦 *{product_name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Before: ~~`EGP {last_price:,.2f}`~~\n"
            f"Now: `EGP {new_price:,.2f}`\n"
            f"Change: {change_text}\n\n"
            f"🔗 [View on Amazon]({url})"
        )

    return message


async def check_prices(bot: Bot):
    products = get_all_products()
    if not products:
        return

    logger.info(f"[scheduler] Checking {len(products)} product(s)...")

    for product_id, url, name, last_price, prev_price, image_url, added_at in products:
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
            authorized_users = get_all_authorized_users_for_notification()
            for user_id, language in authorized_users:
                message = get_localized_notification(product_name, last_price, new_price, url, language)
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.warning(f"[scheduler] Could not send notification to {user_id}: {e}")

            update_price(url, new_price)
            logger.info(f"[scheduler] Price changed for '{product_name}': {last_price} → {new_price}")
        else:
            logger.info(f"[scheduler] No change for '{product_name}': EGP {new_price:,.2f}")


def start_scheduler(bot: Bot, interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_prices,
        trigger="interval",
        minutes=interval_minutes,
        args=[bot],
        id="price_check",
    )
    scheduler.start()
    logger.info(f"[scheduler] Started — checking every {interval_minutes} minute(s).")
    return scheduler
