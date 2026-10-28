"""Owned subprocesses: bounded output, deadline and cancellation cleanup."""
import asyncio
import os
import signal
from pathlib import Path


class MediaError(RuntimeError):
    pass


async def stop(process):
    if process.returncode is None:
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


async def spawn(*args, **kwargs):
    return await asyncio.create_subprocess_exec(
        *map(str, args), start_new_session=os.name == 'posix', **kwargs,
    )


async def read_bounded(stream, limit=4 * 1024 * 1024):
    chunks=[]; size=0
    while chunk := await stream.read(65536):
        size += len(chunk)
        if size > limit:
            raise MediaError('Media process output exceeded limit')
        chunks.append(chunk)
    return b''.join(chunks)


async def run(args, timeout=90, watch_dir: Path | None = None, max_bytes=40*1024*1024):
    process=await spawn(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    async def monitor():
        while process.returncode is None:
            if watch_dir and sum(p.stat().st_size for p in watch_dir.rglob('*') if p.is_file()) > max_bytes:
                raise MediaError('Media files exceeded limit')
            await asyncio.sleep(.25)
    tasks=[asyncio.create_task(read_bounded(process.stdout)), asyncio.create_task(read_bounded(process.stderr)), asyncio.create_task(process.wait())]
    if watch_dir:
        tasks.append(asyncio.create_task(monitor()))
    try:
        output=await asyncio.wait_for(asyncio.gather(*tasks), timeout)
        if process.returncode:
            # Do not expose downloader stderr (it may contain URLs or account data).
            raise MediaError(f'Media process exited with code {process.returncode}')
        return output[0]
    finally:
        await stop(process)
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def in_thread(function, *args):
    """Do not delete job files while a cancelled native analysis still uses them."""
    task=asyncio.create_task(asyncio.to_thread(function,*args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try: await task
        finally: raise
