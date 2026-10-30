from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import numpy as np
from bot.canvas.service import CanvasService
from bot.canvas.process import MediaError
from bot.lastfm import TrackInfo
from bot.themes import DEFAULT


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, count=3, missing=(), fail_upload=False, approximate=False):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        service=CanvasService(temp_dir=str(root))
        service.analyser._load=lambda: None
        items=[TrackInfo(i,f'user{i}',f'user{i}','Artist',f'Song{i}') for i in range(count)]
        message=SimpleNamespace(reply_video=AsyncMock(),reply=AsyncMock())
        message.reply_video.return_value=SimpleNamespace(video=SimpleNamespace(file_id='cached-video'))
        if fail_upload: message.reply_video.side_effect=RuntimeError('upload failed')
        lastfm=SimpleNamespace(call=AsyncMock(return_value=None))
        indices=[]; grids=[]
        async def resolve(artist,title,directory,duration):
            index=int(title[4:])
            if index in missing: raise MediaError('not available')
            directory.mkdir(parents=True); path=directory/'song.wav'; path.touch()
            return SimpleNamespace(path=path,source='YouTube',url=f'https://www.youtube.com/watch?v=demo{index}',approximate=approximate,matched_title='Artist <Live>')
        def frames(items,theme):
            grids.append(len(items)); return SimpleNamespace(width=720,height=768)
        self.came=[]
        async def encode(frames,segment,path,ffmpeg):
            indices.append((segment.index,segment.seconds)); self.came.append(segment.came_from); path.write_bytes(b'video')
        async def join(parts,folder,ffmpeg):
            output=folder/'canvas.mp4'; output.write_bytes(b'combined')
            for p in parts: p.unlink()
            return output
        with patch('bot.canvas.service.resolve_audio',side_effect=resolve), patch('bot.canvas.service.analyse_audio',new=AsyncMock(return_value=(30,np.ones(16000)))), patch('bot.canvas.service.CanvasFrames',side_effect=frames), patch('bot.canvas.service.render_segment',side_effect=encode), patch('bot.canvas.service.join_segments',side_effect=join):
            if fail_upload:
                with self.assertRaises(RuntimeError):
                    await service.send(message,items,DEFAULT,solo=count==1,lastfm=lastfm)
            elif len(missing)==count:
                with self.assertRaises(MediaError):
                    await service.send(message,items,DEFAULT,solo=False,lastfm=lastfm)
            else:
                await service.send(message,items,DEFAULT,solo=count==1,lastfm=lastfm)
        self.assertEqual(list(root.iterdir()),[])
        return service,message,indices,grids,items,lastfm

    async def test_missing_track_skips_only_its_turn(self):
        _,message,indices,grids,_,_=await self.exercise(missing=(1,))
        self.assertEqual(indices,[(0,6),(2,6)])
        self.assertEqual(grids,[3])
        self.assertEqual(message.reply_video.call_args.kwargs['duration'],12)
        self.assertIn('user1',message.reply.call_args.args[0])

    async def test_all_missing_sends_no_silent_video(self):
        _,message,indices,_,_,_=await self.exercise(missing=(0,1,2))
        self.assertFalse(indices); message.reply_video.assert_not_awaited()

    async def test_approximate_match_is_disclosed_and_cached(self):
        service,message,_,_,items,lastfm=await self.exercise(count=1,approximate=True)
        caption=message.reply_video.call_args.kwargs['caption']
        self.assertIn('Аудио заменено',caption)
        self.assertIn('Artist &lt;Live&gt;',caption)
        await service.send(message,items,DEFAULT,solo=True,lastfm=lastfm)
        self.assertEqual(message.reply_video.call_args.kwargs['caption'],caption)

    async def test_whole_group_shares_one_video(self):
        _,message,indices,_,_,_=await self.exercise(count=5)
        self.assertEqual(indices,[(i,6) for i in range(5)])
        self.assertEqual([call.kwargs['duration'] for call in message.reply_video.call_args_list],[30])
        # The video opens fresh; every later clip slides in from the one before it.
        self.assertEqual(self.came,[-1,0,1,2,3])
        caption=message.reply_video.call_args.kwargs['caption']
        for n in range(1,6): self.assertIn(f'{n}. user{n-1}: Artist — Song{n-1}',caption)
        self.assertNotIn('href',caption)

    async def test_group_splits_only_near_upload_limit(self):
        # Each fake clip is 5 bytes: a 14-byte budget fits two clips per video.
        with patch('bot.canvas.service.PART_BYTES',14):
            _,message,indices,_,_,_=await self.exercise(count=5)
        self.assertEqual(indices,[(i,6) for i in range(5)])
        self.assertEqual([call.kwargs['duration'] for call in message.reply_video.call_args_list],[12,12,6])
        self.assertEqual(self.came,[-1,0,-1,2,-1])

    async def test_long_track_list_moves_below_video(self):
        service,message,_,_,items,lastfm=await self.exercise(count=40)
        self.assertEqual(message.reply_video.await_count,1)
        self.assertLessEqual(len(message.reply_video.call_args.kwargs['caption']),1024)
        listed='\n'.join(call.args[0] for call in message.reply.call_args_list)
        for n in range(40): self.assertIn(f'user{n}:',listed)
        message.reply.reset_mock(); message.reply_video.reset_mock()
        await service.send(message,items,DEFAULT,solo=False,lastfm=lastfm)
        self.assertEqual(message.reply_video.call_args.kwargs['video'],'cached-video')
        self.assertIn('user39:','\n'.join(call.args[0] for call in message.reply.call_args_list))

    async def test_transition_skips_missing_card(self):
        await self.exercise(missing=(1,))
        self.assertEqual(self.came,[-1,0])

    async def test_upload_failure_cleans_all_temp_media(self):
        service,_,_,_,_,_=await self.exercise(fail_upload=True)
        self.assertFalse(service.cache)

    async def test_solo_fifteen_seconds_and_cache_uses_file_id(self):
        service,message,indices,_,items,lastfm=await self.exercise(count=1)
        self.assertEqual(indices,[(0,15)])
        lastfm.call.reset_mock()
        await service.send(message,items,DEFAULT,solo=True,lastfm=lastfm)
        self.assertEqual(message.reply_video.call_args.kwargs['video'],'cached-video')
        lastfm.call.assert_not_awaited()
