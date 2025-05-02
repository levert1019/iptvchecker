import sys
import os
import queue
import re
from PyQt5 import QtWidgets, QtCore, QtGui

from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog

# Regex to extract CUID from an EXTINF line
CUID_RE = re.compile(r'CUID="([^\"]+)"')

# Color mapping for console messages
CONSOLE_COLORS = {
    'working': 'green',
    'info': 'blue',
    'error': 'red'
}

class IPTVChecker(QtWidgets.QMainWindow):
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
        self.threads = []
        self.log_records = []  # stores (level, msg, color)
        self._is_paused = False
        self._poll_timer = None

        # Build UI and enforce stylesheet
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

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
        btn_iptv.setCheckable(True); btn_iptv.setChecked(True)
        btn_iptv.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        btn_group.addButton(btn_iptv); bar_layout.addWidget(btn_iptv)

        btn_playlist = QtWidgets.QPushButton("Playlist Sorter")
        btn_playlist.setCheckable(True)
        btn_playlist.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        btn_group.addButton(btn_playlist); bar_layout.addWidget(btn_playlist)

        btn_options = QtWidgets.QPushButton("Options")
        btn_options.setStyleSheet("color:white; background:transparent; border:none;")
        btn_options.clicked.connect(self._open_options)
        bar_layout.addWidget(btn_options)
        bar_layout.addStretch()
        main_v.addWidget(bar)

        # --- Pages ---
        self.pages = QtWidgets.QStackedWidget(); main_v.addWidget(self.pages)

        # IPTV Checker page
        page0 = QtWidgets.QWidget(); pv0 = QtWidgets.QVBoxLayout(page0)
        pv0.setContentsMargins(10,10,10,10); pv0.setSpacing(20)
        hdr0 = QtWidgets.QLabel("DonTV IPTV Checker"); hdr0.setAlignment(QtCore.Qt.AlignCenter)
        pv0.addWidget(hdr0)

        # Control buttons
        ctrl_h = QtWidgets.QHBoxLayout()
        for text, slot in [("Start", self.start_check), ("Pause", self._toggle_pause), ("Stop", self.stop_check)]:
            btn = QtWidgets.QPushButton(text); btn.setFixedSize(130,45); btn.clicked.connect(slot)
            if text == "Pause": self.btn_pause = btn
            ctrl_h.addWidget(btn); ctrl_h.addSpacing(10)
        ctrl_h.addStretch(); pv0.addLayout(ctrl_h)

        # Status tables
        panes = QtWidgets.QHBoxLayout()
        for status in ("working", "black_screen", "non_working"):
            grp = QtWidgets.QGroupBox(status.replace("_"," ").title())
            cols = 3 if status=="working" else 1
            headers = ["Channel","Res","FPS"] if status=="working" else ["Channel"]
            tbl = QtWidgets.QTableWidget(0,cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            panes.addWidget(grp)
        pv0.addLayout(panes)

        # Console
        console_grp = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(console_grp)
        flt_h = QtWidgets.QHBoxLayout()
        for name in ("Show Working","Show Info","Show Error"):
            cb = QtWidgets.QCheckBox(name); cb.setChecked(True); cb.stateChanged.connect(self._refresh_console)
            setattr(self, f"cb_show_{name.split()[1].lower()}", cb); flt_h.addWidget(cb)
        console_v.addLayout(flt_h)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console); pv0.addWidget(console_grp)
        self.pages.addWidget(page0)

        # Playlist Sorter page
        page1 = QtWidgets.QWidget(); pv1 = QtWidgets.QVBoxLayout(page1)
        pv1.setContentsMargins(10,10,10,10); pv1.setSpacing(20)
        hdr1 = QtWidgets.QLabel("DonTV Playlist Sorter"); hdr1.setAlignment(QtCore.Qt.AlignCenter)
        pv1.addWidget(hdr1)
        placeholder = QtWidgets.QLabel("Playlist Sorter functionality coming soon."); placeholder.setAlignment(QtCore.Qt.AlignCenter)
        pv1.addWidget(placeholder); self.pages.addWidget(page1)

        btn_iptv.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        btn_playlist.clicked.connect(lambda: self.pages.setCurrentIndex(1))

        self.status = QtWidgets.QStatusBar(); self.setStatusBar(self.status)

    def _open_options(self):
        # reapply app style before opening
        self.setStyleSheet(STYLE_SHEET)
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        dlg.setStyleSheet(STYLE_SHEET)
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
            dlg.group_urls = self.group_entries; dlg.categories = self.categories
            dlg.selected_groups = list(self.selected_groups); dlg.btn_groups.setEnabled(True)

        result = dlg.exec_()
        # always restore style
        self.setStyleSheet(STYLE_SHEET)
        if result == QtWidgets.QDialog.Accepted:
            opts = dlg.get_options()
            self.m3u_file = opts["m3u_file"]; self.workers = opts["workers"]
            self.retries = opts["retries"]; self.timeout = opts["timeout"]
            self.split = opts["split"]; self.update_quality = opts["update_quality"]
            self.update_fps = opts["update_fps"]; self.include_untested = opts["include_untested"]
            self.output_dir = opts["output_dir"]; self.selected_groups = opts["selected_groups"]

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings", "Please select an M3U file and at least one group.")
            return
        with open(self.m3u_file, "r", encoding="utf-8") as f:
            self.original_lines = f.readlines()
        self.group_entries, self.categories = parse_groups(self.m3u_file)
        for s in ("working","black_screen","non_working"): getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear(); self.te_console.clear()
        self.entry_map = {e["uid"]: e for grp in self.group_entries.values() for e in grp}
        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp,[]): q.put(e.copy())
        self.tasks_q = q
        self.status.showMessage(f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups", 3000)
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q,self.retries,self.timeout)
            t.result.connect(self._on_result); t.log.connect(self._on_log); t.start()
            self.threads.append(t)
        if not self._poll_timer:
            self._poll_timer = QtCore.QTimer(self); self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._monitor_threads); self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        tbl = {"UP": self.tbl_working,"BLACK_SCREEN": self.tbl_black_screen}.get(status, self.tbl_non_working)
        row = tbl.rowCount(); tbl.insertRow(row)
        display = clean_name(entry["name"])
        if status == "UP":
            if self.update_quality and res: display += " " + resolution_to_label(res)
            if self.update_fps and fps is not None: display += " " + format_fps(fps)
        item = QtWidgets.QTableWidgetItem(display); item.setData(QtCore.Qt.UserRole, entry["uid"])
        tbl.setItem(row, 0, item)
        if tbl is self.tbl_working:
            tbl.setItem(row,1,QtWidgets.QTableWidgetItem(res or ""))
            tbl.setItem(row,2,QtWidgets.QTableWidgetItem(str(fps) if fps is not None else ""))

    def _on_log(self, level, msg):
        color = CONSOLE_COLORS.get(level,'black')
        self.log_records.append((level,msg,color)); self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        cursor = self.te_console.textCursor()
        for lvl, m, color in self.log_records:
            show = getattr(self, f"cb_show_{lvl}", None)
            if show and show.isChecked():
                cursor.movePosition(QtGui.QTextCursor.End)
                cursor.insertHtml(f'<span style="color:{color}">{m}</span><br>')
        self.te_console.setTextCursor(cursor)

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads: t.pause() if self._is_paused else t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed",3000)

    def stop_check(self):
        for t in self.threads: t.stop()
        self.status.showMessage("Stopping...",2000)

    def _monitor_threads(self):
        if all(not t.isRunning() for t in self.threads):
            self._poll_timer.stop(); QtCore.QTimer.singleShot(0,self._write_output_files)

    def _write_output_files(self):
        if not self.m3u_file: return
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        outd = self.output_dir or os.getcwd()
        header = "#EXTM3U\n"
        if self.split:
            status_info = [("working","_working"),("black_screen","_blackscreen"),("non_working","_notworking")]
            for status_key,suffix in status_info:
                fn = os.path.join(outd,f"{base}{suffix}.m3u")
                with open(fn,"w",encoding="utf-8") as f:
                    f.write(header)
                    tbl = getattr(self,f"tbl_{status_key}")
                    for row in range(tbl.rowCount()):
                        uid = tbl.item(row,0).data(QtCore.Qt.UserRole)
                        entry = self.entry_map.get(uid)
                        if not entry: continue
                        display = clean_name(entry["name"])
                        if self.update_quality and entry.get("res"): display += " " + resolution_to_label(entry["res"])
                        if self.update_fps and entry.get("fps"): display += " " + format_fps(entry["fps"])
                        attrs = [f'{k}="{entry[k]}"' for k in ("CUID","tvg-name","tvg-id","tvg-logo","group-title") if k in entry]
                        extinf = f"#EXTINF:0 {' '.join(attrs)},{display}\n"
                        f.write(extinf); f.write(entry["url"]+"\n")
                self.status.showMessage(f"Wrote {fn}",5000)
            if self.include_untested:
                fn = os.path.join(outd,f"{base}_all.m3u")
                with open(fn,"w",encoding="utf-8") as f:
                    f.write(header)
                    for ln in self.original_lines:
                        if ln.startswith("#EXTINF") and (m:=CUID_RE.search(ln)):
                            uid = m.group(1); entry = self.entry_map.get(uid)
                            if entry:
                                display = clean_name(entry["name"])
                                if self.update_quality and entry.get("res"): display += " " + resolution_to_label(entry["res"])
                                if self.update_fps and entry.get("fps"): display += " " + format_fps(entry["fps"])
                                attrs = [f'{k}="{entry[k]}"' for k in ("CUID","tvg-name","tvg-id","tvg-logo","group-title") if k in entry]
                                extinf = f"#EXTINF:0 {' '.join(attrs)},{display}\n"
                                f.write(extinf); f.write(entry["url"]+"\n")
                        else: f.write(ln)
                self.status.showMessage(f"Wrote {fn}",5000)
        else:
            fn = os.path.join(outd,f"{base}_all.m3u")
            with open(fn,"w",encoding="utf-8") as f:
                f.write(header)
                for ln in self.original_lines:
                    if ln.startswith("#EXTINF") and (m:=CUID_RE.search(ln)):
                        uid = m.group(1); entry = self.entry_map.get(uid)
                        if entry:
                            display = clean_name(entry["name"])
                            if self.update_quality and entry.get("res"): display += " " + resolution_to_label(entry["res"])
                            if self.update_fps and entry.get("fps"): display += " " + format_fps(entry["fps"])
                            attrs = [f'{k}="{entry[k]}"' for k in ("CUID","tvg-name","tvg-id","tvg-logo","group-title") if k in entry]
                            extinf = f"#EXTINF:0 {' '.join(attrs)},{display}\n"
                            f.write(extinf); f.write(entry["url"]+"\n")
                    else: f.write(ln)
            self.status.showMessage(f"Wrote {fn}",5000)
