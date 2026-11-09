import asyncio
import logging
import os
import re
import time
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "8080"))
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
WORKDIR = Path(os.getenv("DOWNLOAD_DIR", "/tmp/mediavault"))
WORKDIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mediavault")
bot = Bot(TOKEN) if TOKEN else None
dp = Dispatcher()
JOBS = {}
HISTORY = {}

VIDEO_EXT = {".mp4", ".m4v", ".mov", ".mkv", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"}

def clean_name(name):
    name = Path(name or "media.bin").name
    name = re.sub(r"[^\\w.() -]+", "_", name).strip(" .")
    return (name or "media.bin")[:90]

def menu():
    b = InlineKeyboardBuilder()
    b.button(text="Конвертировать файл", callback_data="convert")
    b.button(text="История", callback_data="history")
    b.button(text="Помощь", callback_data="help")
    b.adjust(1)
    return b.as_markup()

def formats():
    b = InlineKeyboardBuilder()
    b.button(text="Видео · MP4", callback_data="fmt:video")
    b.button(text="Аудио · MP3", callback_data="fmt:audio")
    b.button(text="Отмена", callback_data="cancel")
    b.adjust(2, 1)
    return b.as_markup()

async def ffmpeg(source: Path, mode: str) -> Path:
    if mode == "audio":
        target = source.with_suffix(".mp3")
        args = ["ffmpeg", "-y", "-i", str(source), "-vn", "-codec:a", "libmp3lame", "-q:a", "3", str(target)]
    else:
        target = source.with_name(source.stem + "_converted.mp4")
        args = ["ffmpeg", "-y", "-i", str(source), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode or not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("Не удалось преобразовать файл. Проверьте формат и целостность исходника.")
    return target

async def receive_media(message: Message, file_id: str, original_name: str, size: int):
    if size and size > MAX_UPLOAD:
        await message.answer(f"Файл превышает лимит {MAX_UPLOAD // (1024*1024)} МБ.")
        return
    name = clean_name(original_name)
    ext = Path(name).suffix.lower()
    if ext not in VIDEO_EXT | AUDIO_EXT:
        await message.answer("Поддерживаются видео MP4/MOV/MKV/WEBM и аудио MP3/WAV/M4A/OGG/FLAC/AAC.")
        return
    status = await message.answer("Получаю файл…")
    path = WORKDIR / f"{message.from_user.id}_{int(time.time())}_{name}"
    try:
        tgfile = await bot.get_file(file_id)
        await bot.download_file(tgfile.file_path, destination=path)
        JOBS[message.from_user.id] = path
        await status.edit_text(f"<b>{name}</b>\nФайл получен. Выберите результат:", reply_markup=formats(), parse_mode="HTML")
    except Exception:
        path.unlink(missing_ok=True)
        log.exception("Telegram file download failed")
        await status.edit_text("Не удалось получить файл. Попробуйте ещё раз.")

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "<b>MEDIAVAULT</b>  ·  медиаменеджер\n\n"
        "Отправьте свой аудио- или видеофайл документом либо обычным вложением. "
        "Я смогу преобразовать его в MP3 или MP4 и вернуть результат в этот чат.\n\n"
        f"<i>Максимальный размер входящего файла: {MAX_UPLOAD // (1024*1024)} МБ.</i>",
        reply_markup=menu(), parse_mode="HTML"
    )

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Отправьте собственный аудио-/видеофайл, затем выберите MP3 или MP4. Бот не скачивает материалы с YouTube и не обходит ограничения платформ.", reply_markup=menu())

@dp.message(Command("history"))
async def history_cmd(message: Message):
    rows = HISTORY.get(message.from_user.id, [])
    await message.answer("<b>Последние файлы</b>\n" + ("\n".join("• " + x for x in rows) if rows else "История пока пуста."), parse_mode="HTML", reply_markup=menu())

@dp.message(Command("cancel"))
async def cancel_cmd(message: Message):
    p = JOBS.pop(message.from_user.id, None)
    if p: Path(p).unlink(missing_ok=True)
    await message.answer("Операция отменена.", reply_markup=menu())

@dp.callback_query(F.data == "convert")
async def convert_hint(call: CallbackQuery):
    await call.answer()
    await call.message.answer("Пришлите аудио- или видеофайл как документ или вложение.")

@dp.callback_query(F.data == "help")
async def help_callback(call: CallbackQuery):
    await call.answer()
    await call.message.answer("Бот конвертирует загруженные вами файлы. YouTube-загрузчик и обход ограничений платформ не предусмотрены.")

@dp.callback_query(F.data == "history")
async def history_callback(call: CallbackQuery):
    await call.answer()
    rows = HISTORY.get(call.from_user.id, [])
    await call.message.answer("<b>Последние файлы</b>\n" + ("\n".join("• " + x for x in rows) if rows else "История пока пуста."), parse_mode="HTML")

@dp.callback_query(F.data == "cancel")
async def cancel_callback(call: CallbackQuery):
    p = JOBS.pop(call.from_user.id, None)
    if p: Path(p).unlink(missing_ok=True)
    await call.answer("Отменено")
    await call.message.answer("Операция отменена.", reply_markup=menu())

@dp.callback_query(F.data.startswith("fmt:"))
async def format_callback(call: CallbackQuery):
    source = JOBS.get(call.from_user.id)
    if not source or not Path(source).exists():
        await call.answer("Сначала отправьте файл.", show_alert=True)
        return
    source = Path(source)
    mode = call.data.split(":", 1)[1]
    if mode == "video" and source.suffix.lower() not in VIDEO_EXT:
        await call.answer("Для MP4 нужен видеофайл.", show_alert=True)
        return
    await call.answer("Обрабатываю…")
    status = await call.message.answer("Подготавливаю файл…")
    result = None
    try:
        result = await ffmpeg(source, mode)
        if result.stat().st_size > 49 * 1024 * 1024:
            raise ValueError("Результат больше лимита отправки Telegram (49 МБ).")
        await bot.send_chat_action(call.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        await call.message.answer_document(FSInputFile(result), caption="Готово · " + ("MP3" if mode == "audio" else "MP4"))
        size = result.stat().st_size / 1024 / 1024
        HISTORY.setdefault(call.from_user.id, []).insert(0, f"{result.name} · {size:.1f} МБ")
        HISTORY[call.from_user.id] = HISTORY[call.from_user.id][:10]
        await status.edit_text("Готово. Файл отправлен в чат.")
    except Exception as exc:
        await status.edit_text("Не удалось обработать файл: " + str(exc)[:300])
    finally:
        source.unlink(missing_ok=True)
        if result and result != source: result.unlink(missing_ok=True)
        JOBS.pop(call.from_user.id, None)

@dp.message(F.document)
async def document_handler(message: Message):
    d = message.document
    await receive_media(message, d.file_id, d.file_name or "upload.bin", d.file_size or 0)

@dp.message(F.video | F.audio)
async def attachment_handler(message: Message):
    item = message.video or message.audio
    name = getattr(item, "file_name", None) or ("video.mp4" if message.video else "audio.mp3")
    await receive_media(message, item.file_id, name, item.file_size or 0)

async def health(request):
    return web.json_response({"status": "ok", "service": "mediavault"})

async def on_startup(app):
    app["polling"] = asyncio.create_task(dp.start_polling(bot))

async def on_cleanup(app):
    task = app.get("polling")
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in the hosting dashboard.")
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("MediaVault health server listening on %s", PORT)
    try: await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
