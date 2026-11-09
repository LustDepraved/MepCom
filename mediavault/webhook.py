import asyncio
import logging
import os
import secrets

from aiohttp import web
from aiogram.types import Update
from bot import bot, dp, PORT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mediavault.webhook")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
SECRET = os.getenv("WEBHOOK_SECRET") or secrets.token_urlsafe(32)
PATH = "/telegram/webhook"

async def health(request):
    return web.json_response({"status": "ok", "service": "mediavault"})

async def telegram_update(request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        raise web.HTTPUnauthorized(text="Invalid webhook secret")
    try:
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="ok")
    except Exception:
        log.exception("Failed to process Telegram update")
        raise web.HTTPInternalServerError(text="Update processing failed")

async def on_startup(app):
    if BASE_URL:
        await bot.set_webhook(
            BASE_URL + PATH,
            secret_token=SECRET,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        log.info("Telegram webhook registered at %s%s", BASE_URL, PATH)
    else:
        app["polling_task"] = asyncio.create_task(dp.start_polling(bot))
        log.info("No RENDER_EXTERNAL_URL: using polling for local development")

async def on_cleanup(app):
    task = app.get("polling_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await bot.session.close()

async def main():
    if bot is None:
        raise RuntimeError("BOT_TOKEN is missing. Set it in the hosting dashboard.")
    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post(PATH, telegram_update)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("MediaVault server listening on port %s", PORT)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
