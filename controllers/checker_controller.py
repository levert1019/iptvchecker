import os
import queue
import threading
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QTextCursor
from services.parser import parse_groups
from services.workers import WorkerThread
from services.output_writer import write_output_files, CUID_RE
from services.utils import clean_name, resolution_to_label, format_fps

class CheckerController(QtCore.QObject):
    """ IPTV-checking logic, with buffered console and thread-safe UI updates. """
    log_signal = QtCore.pyqtSignal(str, str)  # (level, message)
    status_signal = QtCore.pyqtSignal(str, int)  # (message, timeout_ms)

    def __init__(self, ui, options_dialog, main_window):
        super().__init__(main_window)
        self.ui = ui
        self.opts = options_dialog
        self.main = main_window
        # Default options
        self.m3u_file = ""
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False
        self.output_dir = os.getcwd()
        self.selected_groups = []
        # Runtime state
        self.original_lines = []
        self.group_entries = {}
        self.categories = {}
        self.entry_map = {}
        self.status_map = {}
        self.threads = []
        self._is_paused = False
        # Log buffer
        self.log_records: list[tuple[str, str]] = []
        # Monitor timer
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._monitor_threads)
        # Connect signals
        self.log_signal.connect(self._on_log)
        self.status_signal.connect(self.main.statusBar().showMessage)
        self._connect_signals()

    def _connect_signals(self):
        self.ui.btn_start.clicked.connect(self.start_check)
        self.ui.btn_pause.clicked.connect(self._toggle_pause)
        self.ui.btn_stop.clicked.connect(self.stop_check)
        self.ui.cb_show_working.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_info.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_error.stateChanged.connect(self._refresh_console)

    def start_check(self):
        # Load the latest options
        opts = self.opts.get_options()
        (self.m3u_file, self.workers, self.retries, self.timeout, self.split,
         self.update_quality, self.update_fps, self.include_untested,
         self.output_dir, self.selected_groups) = (
            opts["m3u_file"], opts["workers"], opts["retries"], opts["timeout"],
            opts["split"], opts["update_quality"], opts["update_fps"], opts["include_untested"],
            opts["output_dir"], opts["selected_groups"],
        )
        # Validate
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self.ui, "Missing Settings",
                "Please select an M3U file and at least one group."
            )
            return
        # Read file
        with open(self.m3u_file, "r", encoding="utf-8") as f:
            self.original_lines = f.readlines()
        # Parse groups from M3U file
        raw_group_entries, self.categories = parse_groups(self.m3u_file)
        # Convert dataclass entries to dicts including uid
        converted_entries = {}
        for grp, entries in raw_group_entries.items():
            new_list = []
            for idx, e in enumerate(entries):
                match = CUID_RE.search(e.raw_inf)
                uid = match.group(1) if match else f"{grp}_{idx}"
                entry_dict = {
                    "uid": uid,
                    "name": e.original_name,
                    "url": e.url,
                    "group": e.group,
                    "raw_inf": e.raw_inf,
                    "processed": e.processed,
                    "base": e.base,
                    "ep_suffix": e.ep_suffix,
                }
                new_list.append(entry_dict)
            converted_entries[grp] = new_list
        self.group_entries = converted_entries
        # Reset UI & console
        for tbl in (self.ui.tbl_working, self.ui.tbl_black_screen, self.ui.tbl_non_working):
            tbl.setRowCount(0)
        self.log_records.clear()
        self._refresh_console()
        # Debug: list parsed and selected
        self.log_signal.emit("working", f"[DEBUG] Parsed groups: {list(self.group_entries.keys())}")
        self.log_signal.emit("working", f"[DEBUG] Selected groups: {self.selected_groups}")
        # Match selection
        valid = []
        lookup = {k.lower(): k for k in self.group_entries}
        for sg in self.selected_groups:
            if (key := lookup.get(sg.lower())):
                valid.append(key)
            else:
                matches = [k for k in self.group_entries if sg.lower() in k.lower()]
                if matches:
                    valid.extend(matches)
                    self.log_signal.emit("working", f"[DEBUG] '{sg}' matched {matches}")
                else:
                    self.log_signal.emit("error", f"No match for '{sg}'")
        if not valid:
            valid = list(self.group_entries.keys())
            self.log_signal.emit("working", "[DEBUG] No valid selection; defaulting to ALL groups")
        self.selected_groups = valid
        # Debug: final used groups
        self.log_signal.emit("working", f"[DEBUG] Using groups: {self.selected_groups}")
        # Build entry lookup
        self.entry_map = {
            e["uid"]: e.copy()
            for entries in self.group_entries.values()
            for e in entries
        }
        self.status_map = {}
        # Enqueue tasks
        q = queue.Queue()
        for grp in self.selected_groups:
            for entry in self.group_entries.get(grp, []):
                q.put(entry.copy())
        # Debug queued
        self.log_signal.emit("working", f"[DEBUG] Queued {q.qsize()} entries for checking")
        self.status_signal.emit(f"Queued {q.qsize()} tasks", 3000)
        # Start worker threads
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(lambda lvl, m: self.log_signal.emit(lvl, m))
            t.start()
            self.threads.append(t)
        self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        uid = entry["uid"]
        self.status_map[uid] = status
        # Store resolution and fps
        self.entry_map[uid]["resolution"] = res
        self.entry_map[uid]["fps"] = fps
        # Update name in entry_map for output file (append quality/fps before cleaning)
        name = entry["name"]
        if status == "UP":
            if self.update_quality and (qlbl := resolution_to_label(res)):
                name += f" {qlbl}"
            if self.update_fps and (flbl := format_fps(fps)):
                name += f" {flbl}"
        self.entry_map[uid]["name"] = name
        # Determine display name
        display = clean_name(name)
        # Choose table based on status
        tbl = {"UP": self.ui.tbl_working, "BLACK_SCREEN": self.ui.tbl_black_screen}.get(status, self.ui.tbl_non_working)
        row = tbl.rowCount()
        tbl.insertRow(row)
        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)
        if tbl is self.ui.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(fps)))

    def _on_log(self, level: str, msg: str):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        # Clear text edit
        self.ui.te_console.clear()
        # Group records by level
        categories = {"working": [], "info": [], "error": []}
        for lvl, message in self.log_records:
            if lvl in categories:
                categories[lvl].append(message)
        # Color mapping
        color_map = {"working": "green", "info": "orange", "error": "red"}
        # Iterate in fixed order
        for lvl in ("working", "info", "error"):
            cb = getattr(self.ui, f"cb_show_{lvl}", None)
            if cb and cb.isChecked():
                for message in categories[lvl]:
                    # Move cursor to end and insert HTML with line break
                    cursor = self.ui.te_console.textCursor()
                    cursor.movePosition(QTextCursor.End)
                    cursor.insertHtml(f'<span style="color:{color_map[lvl]};">{message}</span><br>')
                    self.ui.te_console.setTextCursor(cursor)

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
                self.log_signal.emit("info", f"Exported M3U: {p}")
                self.status_signal.emit(f"Exported: {p}", 3000)
        else:
            self.log_signal.emit("info", "No M3U written")
            self.status_signal.emit("No M3U written", 3000)

    # Unified API for MainWindow
    def start(self):
        self.start_check()

    def pause(self):
        self._toggle_pause()

    def stop(self):
        self.stop_check()
