# workers.py
import threading, queue
from PyQt5 import QtCore
from checker import check_stream

class WorkerThread(QtCore.QThread):
    # Now emits exactly 5 values: name, status, res, br, fps
    result = QtCore.pyqtSignal(str, str, str, str, str)
    log    = QtCore.pyqtSignal(str, str)

    def __init__(self, tasks: queue.Queue, retries: int, timeout: float, parent=None):
        super().__init__(parent)
        self.tasks   = tasks
        self.retries = retries
        self.timeout = timeout
        self._pause  = threading.Event()
        self._stop   = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                name, url = self.tasks.get_nowait()
            except queue.Empty:
                break

            # Pause support
            while self._pause.is_set() and not self._stop.is_set():
                self.msleep(100)

            status, res, br, fps = 'DOWN', '–', '–', '–'
            for attempt in range(1, self.retries + 1):
                self.log.emit('info', f"Testing {name} (try {attempt})")
                st, r, b, f = check_stream(name, url, timeout=self.timeout)
                status, res, br, fps = st, r, b, f
                if st == 'UP':
                    self.log.emit('working', f"{name} OK [{r}, {f} FPS, {b}]")
                    break
                elif st == 'BLACK_SCREEN':
                    self.log.emit('error', f"{name} BLACK SCREEN")
                    break
                else:
                    self.log.emit('error', f"{name} DOWN; retrying...")

            # Emit exactly five parts
            self.result.emit(name, status, res, br, fps)

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def stop(self):
        self._stop.set()
        self.resume()
