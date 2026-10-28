import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from bot.handlers.canvas import canvas_mode, handle_canvas
from bot.canvas.service import CanvasService, CanvasBusy
from bot.canvas.process import run


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def test_aliases_exact(self):
        for text in ('/canvas','canvas',' CANVAS ','/canvas@ladsbot'):
            self.assertEqual(canvas_mode(text),'solo')
        for text in ('/npcanvas','/npc','npcanvas','npc','/npc@ladsbot'):
            self.assertEqual(canvas_mode(text),'group')
        for text in ('hello canvas','npc anything','/canvas wrong','canvasanything',None):
            self.assertIsNone(canvas_mode(text))

    async def test_solo_uses_caller_not_group_members(self):
        message=SimpleNamespace(text='/canvas',chat=SimpleNamespace(id=-12,type='group'),from_user=SimpleNamespace(id=42),reply=AsyncMock())
        message.reply.return_value=SimpleNamespace(delete=AsyncMock())
        db=SimpleNamespace(get_user=AsyncMock(return_value={'tg_id':42,'tg_name':'Alice','lastfm_user':'alice'}),get_group_members=AsyncMock(),get_chat_theme=AsyncMock(return_value='default'))
        track=SimpleNamespace(tg_id=42)
        lastfm=SimpleNamespace(fetch_all_now_playing=AsyncMock(return_value=[track]))
        @asynccontextmanager
        async def admit(chat_id): yield
        service=SimpleNamespace(admit=admit,send=AsyncMock())
        await handle_canvas(message,db,lastfm,service)
        db.get_user.assert_awaited_once_with(42)
        db.get_group_members.assert_not_awaited()
        self.assertTrue(service.send.call_args.kwargs['solo'])

    async def test_queue_refuses_duplicate_chat(self):
        service=CanvasService(model_path=Path('unused'))
        async with service.admit(1):
            with self.assertRaises(CanvasBusy):
                async with service.admit(1): pass
        async with service.admit(1): pass

    async def test_timeout_terminates_process(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel=Path(folder)/'finished'
            with self.assertRaises(TimeoutError):
                await run([sys.executable,'-c','import time,pathlib,sys; time.sleep(.8); pathlib.Path(sys.argv[1]).touch()',sentinel],timeout=.1)
            await asyncio.sleep(.9)
            self.assertFalse(sentinel.exists())
