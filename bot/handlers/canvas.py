import asyncio
import logging
import re
from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import Message
from bot.canvas.process import MediaError
from bot.canvas.service import CanvasBusy, CanvasService
from bot.database import Database
from bot.lastfm import LastFMClient
from bot.themes import for_chat

router=Router(name='canvas_router')
log=logging.getLogger(__name__)


def canvas_mode(text):
    if not text: return None
    match=re.fullmatch(r'/?(canvas|npcanvas|npc)(?:@[A-Za-z0-9_]+)?',text.strip(),re.I)
    if not match or ('@' in text and not text.strip().startswith('/')): return None
    return 'solo' if match[1].lower()=='canvas' else 'group'


class CanvasCommand(Filter):
    async def __call__(self,message: Message):
        if not canvas_mode(message.text): return False
        if '@' in message.text:
            mention=message.text.strip().split('@',1)[1]
            me=await message.bot.me()
            return mention.casefold()==(me.username or '').casefold()
        return True


@router.message(CanvasCommand())
async def handle_canvas(message: Message,db: Database,lastfm: LastFMClient,canvas_service: CanvasService):
    if not message.from_user: return
    solo=canvas_mode(message.text)=='solo'
    if not solo and message.chat.type not in {'group','supergroup'}:
        await message.reply('Групповой канвас доступен в группе. Для своего трека — /canvas.'); return
    wait=None
    try:
        async with canvas_service.admit(message.chat.id):
            async with asyncio.timeout(900):
                if solo:
                    user=await db.get_user(message.from_user.id)
                    if not user:
                        await message.reply('Сначала привяжи Last.fm через /reg или /auth в личке бота.'); return
                    members=[user]
                else:
                    await db.add_group_member_if_registered(message.chat.id,message.from_user.id)
                    members=await db.get_group_members(message.chat.id)
                if len(members)>64:
                    await message.reply('Канвас поддерживает до 64 участников за один вызов.'); return
                wait=await message.reply('Собираю 15 секунд твоего трека…' if solo else 'Собираю канвас: треки прозвучат по очереди…')
                items=await lastfm.fetch_all_now_playing(members)
                if not items:
                    await message.reply('Сейчас нет играющего трека.' if solo else 'Сейчас никто ничего не слушает.'); return
                await canvas_service.send(message,items,await for_chat(db,message.chat.id),solo=solo,lastfm=lastfm)
    except CanvasBusy:
        await message.reply('Канвас уже готовится или очередь заполнена. Попробуй чуть позже.')
    except (MediaError,TimeoutError,OSError) as exc:
        log.warning('Canvas request failed (%s)',type(exc).__name__)
        await message.reply('Не удалось собрать канвас: подходящее аудио недоступно или обработка не завершилась. Попробуй позже.')
    finally:
        if wait:
            try: await wait.delete()
            except Exception: pass
