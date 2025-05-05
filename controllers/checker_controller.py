# controllers/checker_controller.py

import os
import queue
import threading
from PyQt5 import QtCore, QtWidgets
from services.parser import parse_groups
from services.workers import WorkerThread
from services.output_writer import write_output_files
from services.utils import clean_name, resolution_to_label, format_fps

class CheckerController(QtCore.QObject):
    """
    IPTV‐checking logic, with buffered console and thread‐safe UI updates.
    """
    # Signals for thread‐safe UI updates
    log_signal    = QtCore.pyqtSignal(str, str)  # (level, message)
    status_signal = QtCore.pyqtSignal(str, int)  # (message, timeout_ms)

    def __init__(self, ui, options_dialog, main_window):
        super().__init__(main_window)
        self.ui   = ui
        self.opts = options_dialog
        self.main = main_window

        # Default options
        self.m3u_file         = ""
        self.workers          = 5
        self.retries          = 2
        self.timeout          = 10
        self.split            = False
        self.update_quality   = False
        self.update_fps       = False
        self.include_untested = False
        self.output_dir       = os.getcwd()
        self.selected_groups  = []

        # Runtime state
        self.original_lines = []
        self.group_entries  = {}
        self.categories     = {}
        self.entry_map      = {}
        self.status_map     = {}
        self.threads        = []
        self._is_paused     = False

        # Buffer for all console logs
        self.log_records: list[tuple[str,str]] = []

        # Poll‐timer to detect when worker threads finish
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._monitor_threads)

        # Connect signals for thread‐safe UI work
        self.log_signal.connect(self._on_log)
        self.status_signal.connect(self.main.statusBar().showMessage)

        self._connect_signals()

    def _connect_signals(self):
        # Buttons
        self.ui.btn_start.clicked.connect(self.start_check)
        self.ui.btn_pause.clicked.connect(self._toggle_pause)
        self.ui.btn_stop.clicked.connect(self.stop_check)
        # Console filter toggles
        self.ui.cb_show_working.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_info   .stateChanged.connect(self._refresh_console)
        self.ui.cb_show_error  .stateChanged.connect(self._refresh_console)

    def start_check(self):
        opts = self.opts.get_options()
        ( self.m3u_file, self.workers, self.retries, self.timeout,
          self.split, self.update_quality, self.update_fps,
          self.include_untested, self.output_dir,
          self.selected_groups ) = (
              opts["m3u_file"], opts["workers"], opts["retries"], opts["timeout"],
              opts["split"], opts["update_quality"], opts["update_fps"],
              opts["include_untested"], opts["output_dir"], opts["selected_groups"]
        )

        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self.ui, "Missing Settings",
                "Please select an M3U file and at least one group."
            )
            return

        # Load & parse
        with open(self.m3u_file, "r", encoding="utf-8") as f:
            self.original_lines = f.readlines()
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        # Clear tables
        for s in ("working", "black_screen", "non_working"):
            getattr(self.ui, f"tbl_{s}").setRowCount(0)

        # Reset console buffer and view
        self.log_records.clear()
        self._refresh_console()

        # Build lookup maps
        self.entry_map = {
            e["uid"]: e.copy()
            for grp in self.group_entries.values()
            for e in grp
        }
        self.status_map = {}

        # Enqueue tasks
        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                q.put(e.copy())

        # Thread‐safe status bar message
        self.status_signal.emit(
            f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups",
            3000
        )

        # Start worker threads
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            # route worker logs through our signal
            t.log.connect(lambda lvl, m: self.log_signal.emit(lvl, m))
            t.start()
            self.threads.append(t)

        self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        uid = entry["uid"]
        self.status_map[uid]              = status
        self.entry_map[uid]["resolution"] = res
        self.entry_map[uid]["fps"]        = fps

        tbl = {
            "UP":           self.ui.tbl_working,
            "BLACK_SCREEN": self.ui.tbl_black_screen
        }.get(status, self.ui.tbl_non_working)

        row = tbl.rowCount()
        tbl.insertRow(row)

        display = clean_name(entry["name"])
        if status == "UP":
            if self.update_quality:
                qlbl = resolution_to_label(res)
                if qlbl: display += " " + qlbl
            if self.update_fps:
                flbl = format_fps(fps)
                if flbl: display += " " + flbl

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)

        if tbl is self.ui.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(fps)))

    def _on_log(self, level: str, msg: str):
        # Buffer every message and re-draw
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.ui.te_console.clear()
        colors = {"working": "green", "info": "orange", "error": "red"}
        for level, msg in self.log_records:
            cb = getattr(self.ui, f"cb_show_{level}", None)
            if cb and cb.isChecked():
                # QTextEdit.append() accepts HTML
                self.ui.te_console.append(f'<span style="color:{colors[level]}">{msg}</span>')

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        txt = "Resume" if self._is_paused else "Pause"
        self.ui.btn_pause.setText(txt)
        self.status_signal.emit(txt, 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        self.status_signal.emit("Stopping...", 2000)

    def _monitor_threads(self):
        if all(not t.isRunning() for t in self.threads):
            self._poll_timer.stop()
            threading.Thread(target=self._write_output, daemon=True).start()

    def _write_output(self):
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        outd = self.output_dir or os.getcwd()
        files = write_output_files(
            self.original_lines,
            self.entry_map,
            self.status_map,
            base,
            outd,
            split=self.split,
            update_quality=self.update_quality,
            update_fps=self.update_fps,
            include_untested=self.include_untested
        )

        if files:
            for p in files:
                # thread‐safe console and status updates
                self.log_signal.emit("info", f"Exported M3U: {p}")
                self.status_signal.emit(f"Exported: {p}", 3000)
        else:
            self.log_signal.emit("info", "No M3U written")
            self.status_signal.emit("No M3U written", 3000)
