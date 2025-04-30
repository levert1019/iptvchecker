import threading, queue
from PyQt5 import QtCore
from checker import check_stream

class WorkerThread(QtCore.QThread):
    """
    Worker thread for checking streams.
    Emits:
      - result(name, status, resolution, fps)
      - log(level, message)
    Levels: 'working', 'info', 'error'
    """
    result = QtCore.pyqtSignal(str, str, str, str)
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

        for attempt in range(1, self.retries + 1):
            self.log.emit('info', f"Testing {name} (try {attempt})")
            st, res, bitrate, fps = check_stream(name, url, timeout=self.timeout)

            if st == 'UP':
                fps_value = fps or '–'
                self.log.emit('working', f"Channel: {name} is WORKING [{res}, {fps_value} FPS]")
                self.result.emit(name, st, res, fps_value)
                break
            elif st == 'BLACK_SCREEN':
                self.log.emit('error', f"Channel: {name} has a BLACK SCREEN")
                self.result.emit(name, st, '–', '–')
                break
            else:
                self.log.emit('error', f"Channel: {name} is DOWN; retrying…")



    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def stop(self):
        self._stop.set()
        self.resume()
