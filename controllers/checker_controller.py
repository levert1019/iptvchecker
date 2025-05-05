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
    Encapsulates all of the IPTV‐checking logic:
      - reading options
      - parsing the M3U
      - spinning up WorkerThreads
      - collecting results into tables
      - exporting M3U(s)
      - console filtering & status‐bar messages
    """
    def __init__(self, ui, options_dialog):
        super().__init__()
        self.ui           = ui
        self.opts         = options_dialog
        # Initialize state
        self.original_lines  = []
        self.group_entries   = {}
        self.categories      = {}
        self.entry_map       = {}
        self.status_map      = {}
        self.threads         = []
        self.log_records     = []
        self._is_paused      = False
        self.selected_groups = []          # <— initialize here
        # Poll‐timer for thread completion
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._monitor_threads)
        self._connect_signals()

    def _connect_signals(self):
        # Button hooks
        self.ui.btn_start.clicked.connect(self.start_check)
        self.ui.btn_pause.clicked.connect(self._toggle_pause)
        self.ui.btn_stop.clicked.connect(self.stop_check)
        # Console filters
        self.ui.cb_show_working.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_info.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_error.stateChanged.connect(self._refresh_console)

    def start_check(self):
        # 1) Read latest options
        opts = self.opts.get_options()
        self.m3u_file        = opts["m3u_file"]
        self.workers         = opts["workers"]
        self.retries         = opts["retries"]
        self.timeout         = opts["timeout"]
        self.split           = opts["split"]
        self.update_quality  = opts["update_quality"]
        self.update_fps      = opts["update_fps"]
        self.include_untested= opts["include_untested"]
        self.output_dir      = opts["output_dir"]
        self.selected_groups = opts["selected_groups"]  # <— capture here

        # 2) Validate
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self.ui, "Missing Settings",
                "Please select an M3U file and at least one group."
            )
            return

        # 3) Load and parse
        with open(self.m3u_file, "r", encoding="utf-8") as f:
            self.original_lines = f.readlines()
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        # 4) Clear UI tables & console
        for status in ("working", "black_screen", "non_working"):
            getattr(self.ui, f"tbl_{status}").setRowCount(0)
        self.log_records.clear()
        self.ui.te_console.clear()

        # 5) Build entry & status maps
        self.entry_map  = {
            e["uid"]: e.copy()
            for grp in self.group_entries.values()
            for e in grp
        }
        self.status_map = {}

        # 6) Enqueue tasks
        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                q.put(e.copy())
        self.tasks_q = q

        # 7) Status bar
        self.ui.statusBar().showMessage(
            f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups", 3000
        )

        # 8) Start worker threads
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # 9) Begin polling for thread completion
        self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        uid = entry["uid"]
        # update our maps
        self.status_map[uid] = status
        self.entry_map[uid]["resolution"] = res
        self.entry_map[uid]["fps"]        = fps

        # pick the right table
        tbl = {
            "UP":           self.ui.tbl_working,
            "BLACK_SCREEN": self.ui.tbl_black_screen
        }.get(status, self.ui.tbl_non_working)

        # insert row
        row = tbl.rowCount()
        tbl.insertRow(row)
        display = clean_name(entry["name"])
        if status == "UP":
            if self.update_quality:
                qlbl = resolution_to_label(res)
                if qlbl:
                    display += " " + qlbl
            if self.update_fps:
                flbl = format_fps(fps)
                if flbl:
                    display += " " + flbl

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)

        if tbl is self.ui.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(fps)))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.ui.te_console.clear()
        show = {
            "working": self.ui.cb_show_working.isChecked(),
            "info":    self.ui.cb_show_info.isChecked(),
            "error":   self.ui.cb_show_error.isChecked()
        }
        for lvl, text in self.log_records:
            if show.get(lvl, False):
                self.ui.te_console.append(text)

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        self.ui.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.ui.statusBar().showMessage(
            "Paused" if self._is_paused else "Resumed", 3000
        )

    def stop_check(self):
        for t in self.threads:
            t.stop()
        self.ui.statusBar().showMessage("Stopping...", 2000)

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
            for path in files:
                self._on_log("info", f"Exported M3U: {path}")
            self.ui.statusBar().showMessage(f"Exported {len(files)} file(s)", 3000)
        else:
            self._on_log("info", "No export options selected; skipping M3U export.")
            self.ui.statusBar().showMessage("No export; no M3U written", 3000)
