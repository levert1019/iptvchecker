import queue
import threading
from PyQt5 import QtCore
from workers import WorkerThread

class CheckerController(QtCore.QObject):
    """
    Orchestrates IPTV checks: start, pause, stop, and dispatch results to the UI.
    """
    # Define custom signals for results and logs
    result_ready = QtCore.pyqtSignal(str, str, str, str)  # name, status, resolution, fps
    log_ready = QtCore.pyqtSignal(str, str)               # level, message
    finished = QtCore.pyqtSignal()

    def __init__(self, window):
        super().__init__()
        self.window = window
        self._workers = []
        self._task_queue = queue.Queue()
        self._running = False
        self._paused = False

    def start(self):
        """Begin processing all selected groups."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self.window.btn_start.setEnabled(False)
        self.window.btn_pause.setEnabled(True)
        self.window.btn_stop.setEnabled(True)


        # Prepare tasks
        for url, name in self.window.selected_groups:
            self._task_queue.put((url, name))

        # Launch worker threads
        for _ in range(self.window.sp_workers.value()):
            t = WorkerThread(
                queue=self._task_queue,
                timeout=self.window.sp_timeout.value(),
                retries=self.window.sp_retries.value()
            )
            t.result.connect(self._emit_result)
            t.log.connect(self._emit_log)
            t.finished.connect(self._worker_finished)
            t.start()
            self._workers.append(t)

    def _emit_result(self, name, status, res, fps):
        self.result_ready.emit(name, status, res, fps)

    def _emit_log(self, level, msg):
        self.log_ready.emit(level, msg)

    def _worker_finished(self):
        """Called each time a worker thread terminates."""
        self._workers.pop()
        if not self._workers:
            self.finished.emit()

    def pause(self):
        """Pause all active workers."""
        if not self._running:
            return
        self._paused = True
        for t in self._workers:
            t.pause()
        self.window.btn_pause.setText("Resume")

    def resume(self):
        """Resume paused workers."""
        if not self._running:
            return
        self._paused = False
        for t in self._workers:
            t.resume()
        self.window.btn_pause.setText("Pause")

    def stop(self):
        """Stop all workers and clear queue."""
        if not self._running:
            return
        self._running = False
        # Signal threads to stop
        for t in self._workers:
            t.stop()
        # Clear any remaining tasks
        with self._task_queue.mutex:
            self._task_queue.queue.clear()

    def is_paused(self):
        return self._paused

    def is_running(self):
        return self._running
