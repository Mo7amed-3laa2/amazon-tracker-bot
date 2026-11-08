import asyncio
import logging
import random
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from database import (
    get_all_products, update_price, get_user_for_product_notification,
    get_user_language, set_product_availability, set_last_scan
)
from formatting import esc, link
from scraper import canonical_product_url, fetch_product

logger = logging.getLogger(__name__)

NL = "\n"

PRICE_CHECK_JOB_ID = "price_check"

# A sweep fetches every tracked product with warm-up and retries, so it can
# run for several minutes; below this the next sweep would collide with the
# one still running (and hammering Amazon is what gets the host IP blocked).
MIN_CHECK_INTERVAL_MINUTES = 10
MAX_CHECK_INTERVAL_MINUTES = 7 * 24 * 60

# Fetching back-to-back is what trips Akamai's bot check on amazon.eg: a
# 42-item sweep that ran in about a minute had a few random items challenged
# on every run. A human-sized gap between products keeps the request rate
# under that threshold.
PRODUCT_DELAY_SECONDS = (4.0, 8.0)
# Items still challenged after their own retries get one more try at the end
# of the sweep, once the burst has had time to cool off, instead of waiting a
# whole interval for the next sweep.
RETRY_COOLDOWN_SECONDS = 60


async def _pause():
    await asyncio.sleep(random.uniform(*PRODUCT_DELAY_SECONDS))


# One sweep at a time. APScheduler's max_instances=1 covers the scheduled job,
# but /check and the menu's check button run a sweep too, and the two must not
# interleave: both write prices, so each would compare against a baseline the
# other has already moved (and double the request rate Amazon sees).
_sweep_lock = asyncio.Lock()


def get_localized_notification(product_name: str, last_price: float, new_price: float, url: str, lang: str, alert_price: float | None = None, product_id: int | None = None) -> str:
    """Generate price notification in user's language.

    Built as HTML: the product name and the Amazon URL both routinely contain
    characters (`_`, `*`, `(`) that Telegram's Markdown parser would either
    reject or silently consume — including inside the link target, which
    leaves the user with a dead link. See formatting.py.
    """
    name = esc(product_name)
    # The id is what /untrack and the list's edit link work off, so an alert
    # is actionable without going back to the list to look the item up.
    id_line = [] if product_id is None else [
        ("🆔 المعرّف: " if lang == "ar" else "🆔 ID: ") + f"<code>{product_id}</code>"
    ]
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
                *id_line,
                f"💰 السعر: <code>EGP {new_price:,.2f}</code>",
                "",
                f"🔗 {amazon_link}",
            ]
        else:
            lines = [
                "📦 <b>New Product</b>",
                "",
                f"<b>{name}</b>",
                *id_line,
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
            *id_line,
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
            *id_line,
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


async def check_prices(bot: Bot, chat_id: str) -> bool:
    """Run one sweep. Returns False if one was already running and this
    trigger was skipped."""
    if _sweep_lock.locked():
        logger.info("[scheduler] Sweep already running — skipping this trigger")
        return False
    async with _sweep_lock:
        await _timed_sweep(bot)
    return True


async def _timed_sweep(bot: Bot):
    products = get_all_products()
    if not products:
        logger.info("[scheduler] No products to check")
        return

    logger.info(f"[scheduler] Checking {len(products)} product(s)...")
    started = time.monotonic()
    stats = {"failed": 0}
    completed = False
    try:
        await _sweep(bot, products, stats)
        completed = True
    finally:
        # Recorded even when the sweep dies part-way, so the admin still sees
        # how long it ran; `completed` tells the two cases apart.
        duration = time.monotonic() - started
        try:
            set_last_scan(duration, len(products), stats["failed"], time.time(), completed)
        except Exception as e:
            logger.error(f"[scheduler] Could not record scan duration: {e}")
        logger.info(f"[scheduler] Sweep of {len(products)} product(s) took {duration:.1f}s")


async def _sweep(bot: Bot, products, stats: dict):
    updated_count = 0

    failed = []
    for i, product_data in enumerate(products):
        if i:
            await _pause()
        outcome = await _check_one(bot, product_data, stats, retry_later=True)
        if outcome == FAILED:
            failed.append(product_data)
        elif outcome == CHANGED:
            updated_count += 1

    if failed:
        logger.info(
            f"[scheduler] Retrying {len(failed)} product(s) that could not be fetched, "
            f"after a {RETRY_COOLDOWN_SECONDS}s cooldown"
        )
        await asyncio.sleep(RETRY_COOLDOWN_SECONDS)
        for i, product_data in enumerate(failed):
            if i:
                await _pause()
            if await _check_one(bot, product_data, stats, retry_later=False) == CHANGED:
                updated_count += 1

    logger.info(f"[scheduler] Check complete: {updated_count} product(s) with price changes")


CHECKED, CHANGED, FAILED = "checked", "changed", "failed"


async def _check_one(bot: Bot, product_data, stats: dict, retry_later: bool) -> str:
    """Check one product and act on its price: CHECKED, CHANGED or FAILED.

    With `retry_later`, a failed fetch is not counted yet: the sweep collects
    those and tries them once more after a cooldown.
    """
    product_id = product_data[0]
    url = product_data[1]
    product_name = product_data[2]
    last_price = product_data[3]
    was_available = product_data[7] if len(product_data) > 7 else 1

    # Blocking network I/O — keep it off the event loop so the bot stays
    # responsive while a scheduled sweep is running.
    result = await asyncio.to_thread(fetch_product, url)
    if result is None:
        if retry_later:
            logger.info(f"[scheduler] Could not fetch {url} — retrying at the end of the sweep")
            return FAILED
        logger.warning(f"[scheduler] Could not fetch: {url}")
        stats["failed"] += 1
        return FAILED

    # Any price still shown on a sold-out page is stale or belongs to
    # another seller's offer, so it is neither notified on nor stored —
    # otherwise the bot alerts on a price nobody can pay and then treats
    # that phantom price as the baseline for the next comparison.
    if not result.get("available", True):
        if was_available:
            logger.info(f"[scheduler] '{product_name}' is now unavailable — holding last known price")
        set_product_availability(url, False)
        return CHECKED

    if not was_available:
        logger.info(f"[scheduler] '{product_name}' is available again")
        set_product_availability(url, True)

    new_price = result["price"]
    is_amazon = result.get("is_amazon", True)

    if last_price is None:
        update_price(url, new_price)
        logger.info(f"[scheduler] Initial price set for '{product_name}': EGP {new_price:,.2f}")
        return CHECKED

    if new_price != last_price:
        price_percent = ((last_price - new_price) / last_price) * 100

        users = get_user_for_product_notification(product_id)
        if not users:
            logger.warning(f"[scheduler] No users tracking product {product_id}")
            update_price(url, new_price)
            return CHECKED

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
                message = get_localized_notification(
                    product_name, last_price, new_price, url, user_lang, alert_price, product_id
                )
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
        logger.info(f"[scheduler] Price changed for '{product_name}': {last_price} -> {new_price} ({price_percent:+.1f}%) [notified {sent_count} user(s)]")
        return CHANGED

    return CHECKED


def start_scheduler(bot: Bot, chat_id: str, interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_prices,
        trigger="interval",
        minutes=interval_minutes,
        args=[bot, chat_id],
        id=PRICE_CHECK_JOB_ID,
        name="Amazon Price Checker",
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"[scheduler] Started - checking every {interval_minutes} minute(s).")
    return scheduler


def reschedule_check(scheduler, interval_minutes: int) -> bool:
    """Apply a new check interval to the running scheduler.

    Returns False when there is no live job to retime (the setting is still
    stored, so it takes effect on the next start).
    """
    if scheduler is None or scheduler.get_job(PRICE_CHECK_JOB_ID) is None:
        logger.warning("[scheduler] No running price_check job to reschedule")
        return False

    scheduler.reschedule_job(PRICE_CHECK_JOB_ID, trigger="interval", minutes=interval_minutes)
    logger.info(f"[scheduler] Rescheduled - now checking every {interval_minutes} minute(s).")
    return True
