import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from database import (
    get_all_products, update_price, get_user_for_product_notification,
    get_user_language
)
from scraper import fetch_product

logger = logging.getLogger(__name__)


def get_localized_notification(product_name: str, last_price: float, new_price: float, url: str, lang: str) -> str:
    """Generate price notification in user's language."""
    if last_price is None or last_price == 0:
        if lang == "ar":
            return (
                f"📦 *منتج جديد*\n\n"
                f"*{product_name}*\n"
                f"💰 السعر: `EGP {new_price:,.2f}`\n\n"
                f"🔗 [عرض على أمازون]({url})"
            )
        else:
            return (
                f"📦 *New Product*\n\n"
                f"*{product_name}*\n"
                f"💰 Price: `EGP {new_price:,.2f}`\n\n"
                f"🔗 [View on Amazon]({url})"
            )

    price_diff = last_price - new_price
    price_percent = (price_diff / last_price) * 100

    if new_price < last_price:
        emoji = "📉"
        if lang == "ar":
            direction = "انخفض"
            change_text = f"💚 *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"
            before_text = "السعر السابق"
            now_text = "السعر الحالي"
            view_text = "عرض على أمازون"
        else:
            direction = "dropped"
            change_text = f"💚 *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"
            before_text = "Before"
            now_text = "Now"
            view_text = "View on Amazon"
    else:
        emoji = "📈"
        if lang == "ar":
            direction = "ارتفع"
            change_text = f"❤️ *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"
            before_text = "السعر السابق"
            now_text = "السعر الحالي"
            view_text = "عرض على أمازون"
        else:
            direction = "increased"
            change_text = f"❤️ *EGP {abs(price_diff):,.2f}* ({abs(price_percent):.1f}%)"
            before_text = "Before"
            now_text = "Now"
            view_text = "View on Amazon"

    if lang == "ar":
        return (
            f"{emoji} *السعر {direction}!*\n\n"
            f"📦 *{product_name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{before_text}: ~~`EGP {last_price:,.2f}`~~\n"
            f"{now_text}: `EGP {new_price:,.2f}`\n"
            f"التغيير: {change_text}\n\n"
            f"🔗 [{view_text}]({url})"
        )
    else:
        return (
            f"{emoji} *Price {direction}!*\n\n"
            f"📦 *{product_name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{before_text}: ~~`EGP {last_price:,.2f}`~~\n"
            f"{now_text}: `EGP {new_price:,.2f}`\n"
            f"Change: {change_text}\n\n"
            f"🔗 [{view_text}]({url})"
        )


async def check_prices(bot: Bot, chat_id: str):
    products = get_all_products()
    if not products:
        logger.info("[scheduler] No products to check")
        return

    logger.info(f"[scheduler] Checking {len(products)} product(s)...")
    updated_count = 0

    for product_data in products:
        product_id = product_data[0]
        url = product_data[1]
        product_name = product_data[2]
        last_price = product_data[3]

        result = fetch_product(url)
        if result is None:
            logger.warning(f"[scheduler] Could not fetch: {url}")
            continue

        new_price = result["price"]

        if last_price is None:
            update_price(url, new_price)
            logger.info(f"[scheduler] Initial price set for '{product_name}': EGP {new_price:,.2f}")
            continue

        if new_price != last_price:
            price_percent = ((last_price - new_price) / last_price) * 100

            users = get_user_for_product_notification(product_id)
            if not users:
                logger.warning(f"[scheduler] No users tracking product {product_id}")
                update_price(url, new_price)
                continue

            sent_count = 0
            for user_id, user_lang in users:
                try:
                    message = get_localized_notification(product_name, last_price, new_price, url, user_lang)
                    await bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"[scheduler] Failed to send notification to user {user_id}: {e}")

            update_price(url, new_price)
            updated_count += 1
            logger.info(f"[scheduler] Price changed for '{product_name}': {last_price} → {new_price} ({price_percent:+.1f}%) [notified {sent_count} user(s)]")

    logger.info(f"[scheduler] Check complete: {updated_count} product(s) with price changes")


def start_scheduler(bot: Bot, chat_id: str, interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_prices,
        trigger="interval",
        minutes=interval_minutes,
        args=[bot, chat_id],
        id="price_check",
        name="Amazon Price Checker",
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"[scheduler] Started — checking every {interval_minutes} minute(s).")
    return scheduler
