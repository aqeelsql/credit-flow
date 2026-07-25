import asyncio
import logging
from contextlib import suppress

from app.config import Settings
from app.due_scanner import scan_due_posts


class EmbeddedDuePostScanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def start(self) -> None:
        if not self.settings.embedded_scanner_enabled:
            logging.info("Scheduler embedded due-post scanner is disabled.")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="scheduler-embedded-due-post-scanner")
        logging.info("Scheduler embedded due-post scanner started; interval=%ss", self.settings.scan_interval_seconds)

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                result = await asyncio.to_thread(scan_due_posts)
                if result.get("dispatched") or result.get("skipped_locked"):
                    logging.info("Scheduler due-post scan result: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.exception("Scheduler embedded due-post scan failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(5, self.settings.scan_interval_seconds))
            except asyncio.TimeoutError:
                continue
