import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from database import (
    get_all_products, update_price, get_user_for_product_notification,
    get_user_language, set_product_availability
)
from formatting import esc, link
from scraper import canonical_product_url, fetch_product

logger = logging.getLogger(__name__)

NL = "\n"


def get_localized_notification(product_name: str, last_price: float, new_price: float, url: str, lang: str, alert_price: float | None = None) -> str:
    """Generate price notification in user's language.

    Built as HTML: the product name and the Amazon URL both routinely contain
    characters (`_`, `*`, `(`) that Telegram's Markdown parser would either
    reject or silently consume — including inside the link target, which
    leaves the user with a dead link. See formatting.py.
    """
    name = esc(product_name)
    amazon_link = link(
        "عرض على أمازون" if lang == "ar" else "View on Amazon",
        canonical_product_url(url),
    )

    if last_price is None or last_price == 0:
        if lang == "ar":
            lines = [
                "📦 <b>منتج جديد</b>",
                "",
                f"<b>{name}</b>",
                f"💰 السعر: <code>EGP {new_price:,.2f}</code>",
                "",
                f"🔗 {amazon_link}",
            ]
        else:
            lines = [
                "📦 <b>New Product</b>",
                "",
                f"<b>{name}</b>",
                f"💰 Price: <code>EGP {new_price:,.2f}</code>",
                "",
                f"🔗 {amazon_link}",
            ]
        return NL.join(lines)

    price_diff = last_price - new_price
    price_percent = (price_diff / last_price) * 100
    dropped = new_price < last_price
    emoji = "📉" if dropped else "📈"
    change_text = ("💚" if dropped else "❤️") + f" <b>EGP {abs(price_diff):,.2f}</b> ({abs(price_percent):.1f}%)"

    lines = []
    if lang == "ar":
        if alert_price is not None:
            lines += [f"🚨 <b>وصل إلى سعرك المستهدف <code>EGP {alert_price:,.2f}</code>!</b>", ""]
        lines += [
            f"{emoji} <b>السعر {'انخفض' if dropped else 'ارتفع'}!</b>",
            "",
            f"📦 <b>{name}</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"السعر السابق: <s>EGP {last_price:,.2f}</s>",
            f"السعر الحالي: <code>EGP {new_price:,.2f}</code>",
            f"التغيير: {change_text}",
            "",
            f"🔗 {amazon_link}",
        ]
    else:
        if alert_price is not None:
            lines += [f"🚨 <b>Hit your target price of <code>EGP {alert_price:,.2f}</code>!</b>", ""]
        lines += [
            f"{emoji} <b>Price {'dropped' if dropped else 'increased'}!</b>",
            "",
            f"📦 <b>{name}</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"Before: <s>EGP {last_price:,.2f}</s>",
            f"Now: <code>EGP {new_price:,.2f}</code>",
            f"Change: {change_text}",
            "",
            f"🔗 {amazon_link}",
        ]
    return NL.join(lines)


def _should_notify_user(alert_price: float | None, require_amazon: bool, new_price: float, is_amazon: bool) -> bool:
    """Decide whether this user wants an alert for the new price.

    alert_price is a ceiling: with one set, only prices at or below it notify.
    With none set, every price change notifies (the original behaviour).
    """
    if require_amazon and not is_amazon:
        return False

    if alert_price is not None and new_price > alert_price:
        return False

    return True


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
        was_available = product_data[7] if len(product_data) > 7 else 1

        # Blocking network I/O — keep it off the event loop so the bot stays
        # responsive while a scheduled sweep is running.
        result = await asyncio.to_thread(fetch_product, url)
        if result is None:
            logger.warning(f"[scheduler] Could not fetch: {url}")
            continue

        # Any price still shown on a sold-out page is stale or belongs to
        # another seller's offer, so it is neither notified on nor stored —
        # otherwise the bot alerts on a price nobody can pay and then treats
        # that phantom price as the baseline for the next comparison.
        if not result.get("available", True):
            if was_available:
                logger.info(f"[scheduler] '{product_name}' is now unavailable — holding last known price")
            set_product_availability(url, False)
            continue

        if not was_available:
            logger.info(f"[scheduler] '{product_name}' is available again")
            set_product_availability(url, True)

        new_price = result["price"]
        is_amazon = result.get("is_amazon", True)

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
            for user_id, user_lang, price_min, alert_price, require_amazon in users:
                if not _should_notify_user(alert_price, require_amazon, new_price, is_amazon):
                    logger.debug(
                        f"[scheduler] Skipping notification for user {user_id}: "
                        f"price={new_price}, alert={alert_price}, "
                        f"is_amazon={is_amazon}, require_amazon={require_amazon}"
                    )
                    continue

                try:
                    message = get_localized_notification(product_name, last_price, new_price, url, user_lang, alert_price)
                    await bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"[scheduler] Failed to send notification to user {user_id}: {e}")

            update_price(url, new_price)
            updated_count += 1
            logger.info(f"[scheduler] Price changed for '{product_name}': {last_price} -> {new_price} ({price_percent:+.1f}%) [notified {sent_count} user(s)]")

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
    logger.info(f"[scheduler] Started - checking every {interval_minutes} minute(s).")
    return scheduler
