import sys
import os
import queue
import threading
import re
from PyQt5 import QtWidgets, QtCore
from services.parser import parse_groups
from services.workers import WorkerThread
from services.utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog
from services.output_writer import write_output_files
from services.playlist_sorter import sort_entries, write_sorted

# Regex to extract CUID from an EXTINF line
CUID_RE = re.compile(r'CUID="([^"]+)"')

class IPTVChecker(QtWidgets.QMainWindow):
    # Signals for thread-safe UI updates
    export_log    = QtCore.pyqtSignal(str, str)   # level, message
    export_status = QtCore.pyqtSignal(str, int)   # message, timeout_ms

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker & Playlist Sorter")
        self.resize(1000, 700)

        # --- Core state ---
        self.m3u_file = ""
        self.original_lines = []
        self.group_entries = {}
        self.categories = {}
        self.selected_groups = []

        # --- Options defaults ---
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False
        self.output_dir = os.getcwd()

        # --- Runtime ---
        self.entry_map = {}
        self.status_map = {}
        self.threads = []
        self.log_records = []
        self._is_paused = False
        self._poll_timer = None

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

        # Connect signals for UI updates
        self.export_log.connect(self._on_log)
        self.export_status.connect(self.status.showMessage)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(0)

        # --- Script switcher bar ---
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #5b2fc9;")
        bar_layout = QtWidgets.QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 0, 0, 0)
        btn_group = QtWidgets.QButtonGroup(self)

        btn_iptv = QtWidgets.QPushButton("IPTV Checker")
        btn_iptv.setCheckable(True)
        btn_iptv.setChecked(True)
        btn_iptv.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        btn_group.addButton(btn_iptv)
        bar_layout.addWidget(btn_iptv)

        btn_playlist = QtWidgets.QPushButton("Playlist Sorter")
        btn_playlist.setCheckable(True)
        btn_playlist.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        btn_group.addButton(btn_playlist)
        bar_layout.addWidget(btn_playlist)

        btn_options = QtWidgets.QPushButton("Options")
        btn_options.setStyleSheet("color:white; background:transparent; border:none;")
        btn_options.clicked.connect(self._open_options)
        bar_layout.addWidget(btn_options)

        bar_layout.addStretch()
        main_v.addWidget(bar)

        # --- Pages container ---
        self.pages = QtWidgets.QStackedWidget()
        main_v.addWidget(self.pages)

        # --- Page 0: IPTV Checker ---
        page0 = QtWidgets.QWidget()
        pv0 = QtWidgets.QVBoxLayout(page0)
        pv0.setContentsMargins(10, 10, 10, 10)
        pv0.setSpacing(20)

        # Header
        hdr0 = QtWidgets.QLabel()
        hdr0.setTextFormat(QtCore.Qt.RichText)
        hdr0.setText(
            '<span style="font-size:24pt; color:#FFFFFF; font-weight:bold;">Don</span>'
            '<span style="font-size:24pt; color:#5b2fc9; font-weight:bold;">TV</span>'
            '<span style="font-size:18pt; color:#FFFFFF; font-weight:bold;"> IPTV Checker</span>'
        )
        hdr0.setAlignment(QtCore.Qt.AlignCenter)
        pv0.addWidget(hdr0)

        # Controls
        ctrl_h = QtWidgets.QHBoxLayout()
        for text, slot in [("Start", self.start_check),
                           ("Pause", self._toggle_pause),
                           ("Stop", self.stop_check)]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(130, 45)
            btn.clicked.connect(slot)
            if text == "Pause":
                self.btn_pause = btn
            ctrl_h.addWidget(btn)
            ctrl_h.addSpacing(10)
        ctrl_h.addStretch()
        pv0.addLayout(ctrl_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ("working", "black_screen", "non_working"):
            grp = QtWidgets.QGroupBox(status.replace("_", " ").title())
            cols = 3 if status == "working" else 1
            headers = ["Channel", "Res", "FPS"] if status == "working" else ["Channel"]
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            panes.addWidget(grp)
        pv0.addLayout(panes)

        # Console + filters
        console_grp = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(console_grp)
        flt_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_console)
            flt_h.addWidget(cb)
        console_v.addLayout(flt_h)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)
        pv0.addWidget(console_grp)

        self.pages.addWidget(page0)

        # --- Page 1: Playlist Sorter ---
        page1 = QtWidgets.QWidget()
        pv1   = QtWidgets.QVBoxLayout(page1)
        pv1.setContentsMargins(10, 10, 10, 10)
        pv1.setSpacing(20)

        # Header
        hdr1 = QtWidgets.QLabel()
        hdr1.setTextFormat(QtCore.Qt.RichText)
        hdr1.setText(
            '<span style="font-size:24pt; color:#FFFFFF; font-weight:bold;">Don</span>'
            '<span style="font-size:24pt; color:#5b2fc9; font-weight:bold;">TV</span>'
            '<span style="font-size:18pt; color:#FFFFFF; font-weight:bold;"> Playlist Sorter</span>'
        )
        hdr1.setAlignment(QtCore.Qt.AlignCenter)
        pv1.addWidget(hdr1)

        # File selector
        h_file = QtWidgets.QHBoxLayout()
        self.le_sort_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_sort_file)
        h_file.addWidget(self.le_sort_m3u)
        h_file.addWidget(btn_browse)
        pv1.addLayout(h_file)

        # Group-order tree
        self.tree_groups = QtWidgets.QTreeWidget()
        self.tree_groups.setHeaderLabels(["Group Name"])
        self.tree_groups.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        pv1.addWidget(self.tree_groups, 1)

        # Sort options
        opt_h = QtWidgets.QHBoxLayout()
        self.cb_alpha = QtWidgets.QCheckBox("Sort channels alphabetically")
        self.cb_alpha.setChecked(True)
        opt_h.addWidget(self.cb_alpha)
        opt_h.addStretch()
        pv1.addLayout(opt_h)

        # Generate button
        btn_sort = QtWidgets.QPushButton("Generate Sorted Playlist")
        btn_sort.clicked.connect(self._run_sorter)
        pv1.addWidget(btn_sort)

        self.pages.addWidget(page1)

        # Page switching
        btn_iptv.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        btn_playlist.clicked.connect(lambda: self.pages.setCurrentIndex(1))

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _open_options(self):
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        dlg.le_m3u.setText(self.m3u_file)
        dlg.sp_workers.setValue(self.workers)
        dlg.sp_retries.setValue(self.retries)
        dlg.sp_timeout.setValue(self.timeout)
        dlg.cb_split.setChecked(self.split)
        dlg.cb_update_quality.setChecked(self.update_quality)
        dlg.cb_update_fps.setChecked(self.update_fps)
        dlg.cb_include_untested.setChecked(self.include_untested)
        dlg.le_out.setText(self.output_dir)
        if self.m3u_file:
            self.group_entries, self.categories = parse_groups(self.m3u_file)
            dlg.group_urls = self.group_entries
            dlg.categories = self.categories
            dlg.selected_groups = list(self.selected_groups)
            dlg.btn_groups.setEnabled(True)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            opts = dlg.get_options()
            self.m3u_file = opts["m3u_file"]
            self.workers = opts["workers"]
            self.retries = opts["retries"]
            self.timeout = opts["timeout"]
            self.split = opts["split"]
            self.update_quality = opts["update_quality"]
            self.update_fps = opts["update_fps"]
            self.include_untested = opts["include_untested"]
            self.output_dir = opts["output_dir"]
            self.selected_groups = opts["selected_groups"]

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "Missing Settings",
                "Please select an M3U file and at least one group."
            )
            return

        with open(self.m3u_file, "r", encoding="utf-8") as f:
            self.original_lines = f.readlines()
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        for s in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        self.entry_map = {
            e["uid"]: e.copy()
            for grp in self.group_entries.values()
            for e in grp
        }
        self.status_map = {}

        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                q.put(e.copy())
        self.tasks_q = q

        self.status.showMessage(
            f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups",
            3000
        )

        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        if not self._poll_timer:
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._monitor_threads)
            self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        uid = entry["uid"]
        self.status_map[uid] = status
        self.entry_map[uid]["resolution"] = res
        self.entry_map[uid]["fps"] = fps

        tbl = {
            "UP": self.tbl_working,
            "BLACK_SCREEN": self.tbl_black_screen
        }.get(status, self.tbl_non_working)

        row = tbl.rowCount()
        tbl.insertRow(row)
        display = clean_name(entry["name"])
        if status == "UP":
            if self.update_quality:
                q = resolution_to_label(res)
                if q:
                    display += " " + q
            if self.update_fps:
                f = format_fps(fps)
                if f:
                    display += " " + f

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)

        if tbl is self.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(fps)))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show = {
            "working": self.cb_show_working.isChecked(),
            "info": self.cb_show_info.isChecked(),
            "error": self.cb_show_error.isChecked()
        }
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(m)

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed", 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        self.status.showMessage("Stopping...", 2000)

    def _monitor_threads(self):
        if all(not t.isRunning() for t in self.threads):
            self._poll_timer.stop()
            threading.Thread(target=self._write_output_files, daemon=True).start()

    def _write_output_files(self):
        """Run in background thread; emit signals instead of touching UI directly."""
        if not self.m3u_file:
            return

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
            for fpath in files:
                self.export_log.emit("info", f"Exported M3U: {fpath}")
            self.export_status.emit(f"Exported {len(files)} file(s)", 3000)
        else:
            self.export_log.emit("info", "No export options selected; skipping M3U export.")
            self.export_status.emit("No export options; no M3U written", 3000)

    def _browse_sort_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U to sort", filter="*.m3u"
        )
        if path:
            self.le_sort_m3u.setText(path)
            groups, _ = parse_groups(path)
            self.tree_groups.clear()
            for grp in groups:
                item = QtWidgets.QTreeWidgetItem([grp])
                self.tree_groups.addTopLevelItem(item)

    def _run_sorter(self):
        m3u = self.le_sort_m3u.text()
        if not m3u:
            QtWidgets.QMessageBox.warning(
                self, "Missing File", "Please pick an M3U first."
            )
            return

        group_order = [
            self.tree_groups.topLevelItem(i).text(0)
            for i in range(self.tree_groups.topLevelItemCount())
        ]
        key = "name" if self.cb_alpha.isChecked() else "uid"
        lines = sort_entries(m3u, group_order, channel_sort_key=key)
        out_path = os.path.splitext(m3u)[0] + "_sorted.m3u"
        write_sorted(lines, out_path)
        self.status.showMessage(f"Sorted playlist written to {out_path}", 3000)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
