import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import themes
from bot.database import Database

logger = logging.getLogger(__name__)

router = Router(name="themes_router")

PREFIX = "theme:"


def _label(key: str) -> str:
    t = themes.THEMES[key]
    return f"{t.emoji} {t.title}"


def _keyboard(current: str) -> InlineKeyboardMarkup:
    keys = themes.ORDER
    buttons = [
        InlineKeyboardButton(text=("✅ " if k == current else "") + _label(k), callback_data=PREFIX + k)
        for k in keys
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def _line(key: str) -> str:
    t = themes.THEMES[key]
    return f"{t.emoji} <b>{t.title}</b> — {t.blurb}"


def _is_light(key: str) -> bool:
    r, g, b = themes.THEMES[key].bg
    return 0.299 * r + 0.587 * g + 0.114 * b > 140


def _text(current: str) -> str:
    current = themes.resolve(current).key
    dark = "\n".join(_line(k) for k in themes.ORDER if not _is_light(k))
    light = "\n".join(_line(k) for k in themes.ORDER if _is_light(k))
    return (
        "🎨 <b>Тема оформления</b>\n"
        "Меняет стиль и структуру коллажа <code>/np</code> и всех картинок со статистикой в этом чате.\n\n"
        f"🌙 <b>Тёмные</b>\n{dark}\n\n"
        f"☀️ <b>Светлые</b>\n{light}\n\n"
        f"Выбрано: <b>{_label(current)}</b>"
    )


async def _can_change(bot, chat_id: int, chat_type: str, user_id: int) -> bool:
    if chat_type == "private":
        return True
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ("creator", "administrator")


@router.message(Command("themes", "theme"))
async def cmd_themes(message: Message, db: Database) -> None:
    current = themes.resolve(await db.get_chat_theme(message.chat.id)).key
    await message.answer(_text(current), reply_markup=_keyboard(current), parse_mode="HTML")


@router.callback_query(F.data.startswith(PREFIX))
async def on_theme_pick(query: CallbackQuery, db: Database) -> None:
    key = (query.data or "")[len(PREFIX):]
    msg = query.message
    if key not in themes.THEMES:
        await query.answer("Неизвестная тема")
        return
    if not msg:
        await query.answer()
        return
    try:
        allowed = await _can_change(query.bot, msg.chat.id, msg.chat.type, query.from_user.id)
    except Exception as e:
        logger.warning("Admin check failed in chat %s: %s", msg.chat.id, e)
        allowed = False
    if not allowed:
        await query.answer("Менять тему могут только админы чата", show_alert=True)
        return
    if key == themes.resolve(await db.get_chat_theme(msg.chat.id)).key:
        await query.answer("Эта тема уже выбрана")
        return
    await db.set_chat_theme(msg.chat.id, key)
    await query.answer(f"Тема: {_label(key)}")
    try:
        await msg.edit_text(_text(key), reply_markup=_keyboard(key), parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to update themes message: %s", e)
