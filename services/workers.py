# services/workers.py

import threading
import queue

from PyQt5 import QtCore
from checker import check_stream

class WorkerThread(QtCore.QThread):
    """
    Worker thread for checking streams.

    Emits:
    - result(entry, status, resolution, fps)
    - log(level, message)

    Levels: 'working', 'error'
    """
    result = QtCore.pyqtSignal(object, str, str, str)
    log = QtCore.pyqtSignal(str, str)

    def __init__(self, tasks: queue.Queue, retries: int, timeout: float, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.retries = retries
        self.timeout = timeout
        self._pause = threading.Event()
        self._stop = threading.Event()

    def run(self):
        # Signal that this thread is alive
        self.log.emit('working', '[WORKER] Thread started')

        # Process tasks until none remain or stopped
        while not self._stop.is_set():
            try:
                entry = self.tasks.get_nowait()
            except queue.Empty:
                break

            name = entry.get('name', '<no-name>')
            url  = entry.get('url', '')

            # Honor pause
            while self._pause.is_set() and not self._stop.is_set():
                self.msleep(100)

            # Try checking the stream up to `retries` times
            for attempt in range(1, self.retries + 1):
                self.log.emit('working', f"[WORKER] Testing {name} (try {attempt})")
                try:
                    st, res, bitrate, fps = check_stream(name, url, timeout=self.timeout)
                except Exception as e:
                    self.log.emit('error', f"[WORKER] Exception testing {name}: {e}")
                    self.result.emit(entry, 'DOWN', '–', '–')
                    break

                if st == 'UP':
                    fps_value = fps or '–'
                    self.log.emit('working', f"Channel: {name} is WORKING [{res}, {fps_value} FPS]")
                    self.result.emit(entry, st, res, fps_value)
                    break

                elif st == 'BLACK_SCREEN':
                    self.log.emit('error', f"Channel: {name} has a BLACK SCREEN")
                    self.result.emit(entry, st, '–', '–')
                    break

                else:  # DOWN
                    if attempt < self.retries:
                        self.log.emit('error', f"Channel: {name} is DOWN; retrying…")
                    else:
                        self.log.emit('error', f"Channel: {name} is DOWN after {self.retries} retries")
                        self.result.emit(entry, 'DOWN', '–', '–')

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def stop(self):
        self._stop.set()
        self.resume()
