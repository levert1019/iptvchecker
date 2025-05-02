# main_window.py

import sys
import os
import queue
import threading
import re
from PyQt5 import QtWidgets, QtCore, QtGui

from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog
from output_writer import write_output_files

class IPTVChecker(QtWidgets.QMainWindow):
    fileWritten = QtCore.pyqtSignal(str)
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
        self.entry_map = {}        # uid -> entry dict
        self.status_map = {}       # uid -> status string
        self.threads = []
        self.log_records = []      # (level, msg, color)
        self._is_paused = False
        self._poll_timer = None

        # Signal → GUI console
        self.fileWritten.connect(lambda fn: self._on_log('info', f"Wrote {fn}"))

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10,10,10,10)
        main_v.setSpacing(0)

        # --- Script switcher bar ---
        bar = QtWidgets.QFrame(); bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #5b2fc9;")
        bar_layout = QtWidgets.QHBoxLayout(bar); bar_layout.setContentsMargins(10,0,0,0)
        btn_group = QtWidgets.QButtonGroup(self)

        btn_iptv = QtWidgets.QPushButton("IPTV Checker"); btn_iptv.setCheckable(True); btn_iptv.setChecked(True)
        btn_iptv.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        btn_group.addButton(btn_iptv); bar_layout.addWidget(btn_iptv)

        btn_playlist = QtWidgets.QPushButton("Playlist Sorter"); btn_playlist.setCheckable(True)
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

        # Page 0: IPTV Checker
        page0 = QtWidgets.QWidget(); pv0 = QtWidgets.QVBoxLayout(page0)
        pv0.setContentsMargins(10,10,10,10); pv0.setSpacing(20)
        hdr0 = QtWidgets.QLabel("DonTV IPTV Checker"); hdr0.setAlignment(QtCore.Qt.AlignCenter)
        pv0.addWidget(hdr0)

        # Control buttons
        ctrl_h = QtWidgets.QHBoxLayout()
        for text, slot in [("Start", self.start_check), ("Pause", self._toggle_pause), ("Stop", self.stop_check)]:
            btn = QtWidgets.QPushButton(text); btn.setFixedSize(130,45); btn.clicked.connect(slot)
            if text=="Pause": self.btn_pause = btn
            ctrl_h.addWidget(btn); ctrl_h.addSpacing(10)
        ctrl_h.addStretch(); pv0.addLayout(ctrl_h)

        # Status tables
        panes = QtWidgets.QHBoxLayout()
        for status in ("working","black_screen","non_working"):
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
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True)
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info");    self.cb_show_info.setChecked(True)
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error");   self.cb_show_error.setChecked(True)
        for cb in (self.cb_show_working,self.cb_show_info,self.cb_show_error):
            cb.stateChanged.connect(self._refresh_console); flt_h.addWidget(cb)
        console_v.addLayout(flt_h)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)
        pv0.addWidget(console_grp)

        self.pages.addWidget(page0)

        # Page 1: Playlist Sorter placeholder
        page1 = QtWidgets.QWidget()
        pv1 = QtWidgets.QVBoxLayout(page1)
        pv1.setContentsMargins(10,10,10,10); pv1.setSpacing(20)
        hdr1 = QtWidgets.QLabel("DonTV Playlist Sorter"); hdr1.setAlignment(QtCore.Qt.AlignCenter)
        pv1.addWidget(hdr1)
        placeholder = QtWidgets.QLabel("Playlist Sorter functionality coming soon.")
        placeholder.setAlignment(QtCore.Qt.AlignCenter)
        pv1.addWidget(placeholder)
        self.pages.addWidget(page1)

        # Navigation
        btn_iptv.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        btn_playlist.clicked.connect(lambda: self.pages.setCurrentIndex(1))

        # Status bar
        self.status = QtWidgets.QStatusBar(); self.setStatusBar(self.status)


    def _open_options(self):
        self.setStyleSheet(STYLE_SHEET)
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        dlg.setStyleSheet(STYLE_SHEET)
        # populate...
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

        result = dlg.exec_()
        self.setStyleSheet(STYLE_SHEET)
        if result == QtWidgets.QDialog.Accepted:
            opts = dlg.get_options()
            self.m3u_file        = opts["m3u_file"]
            self.workers         = opts["workers"]
            self.retries         = opts["retries"]
            self.timeout         = opts["timeout"]
            self.split           = opts["split"]
            self.update_quality  = opts["update_quality"]
            self.update_fps      = opts["update_fps"]
            self.include_untested= opts["include_untested"]
            self.output_dir      = opts["output_dir"]
            self.selected_groups = opts["selected_groups"]


    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings", "Please select an M3U file and at least one group.")
            return

        # load original lines & reset state
        with open(self.m3u_file, 'r', encoding='utf-8') as f:
            self.original_lines = f.readlines()

        self.group_entries, self.categories = parse_groups(self.m3u_file)
        for s in ("working","black_screen","non_working"):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear(); self.te_console.clear()
        self.entry_map.clear(); self.status_map.clear()

        # prepare entry & status maps
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                uid = e["uid"]
                self.entry_map[uid]  = e
                self.status_map[uid] = 'UNTESTED'

        # queue tasks
        q = queue.Queue()
        for e in self.entry_map.values():
            q.put(e.copy())
        self.tasks_q = q

        self.status.showMessage(f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups", 3000)

        # start worker threads
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # poll for completion
        if not self._poll_timer:
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._monitor_threads)
            self._poll_timer.start()


    def _on_result(self, entry, status, res, fps):
        uid = entry['uid']
        self.status_map[uid] = status

        tbl = {"UP": self.tbl_working, "BLACK_SCREEN": self.tbl_black_screen}.get(status, self.tbl_non_working)
        row = tbl.rowCount()
        tbl.insertRow(row)

        display = clean_name(entry["name"])
        if status == "UP":
            if self.update_quality and res:
                display += " " + resolution_to_label(res)
            if self.update_fps and fps is not None:
                display += " " + format_fps(fps)

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)

        if tbl is self.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res or ""))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(fps) if fps is not None else ""))


    def _on_log(self, level, msg):
        COLORS = {'working':'green','info':'orange','error':'red'}
        color = COLORS.get(level, 'black')
        self.log_records.append((level, msg, color))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        cursor = self.te_console.textCursor()
        for lvl, m, color in self.log_records:
            cb = getattr(self, f"cb_show_{lvl}", None)
            if cb and cb.isChecked():
                cursor.movePosition(QtGui.QTextCursor.End)
                cursor.insertHtml(f'<span style="color:{color}">{m}</span><br>')
        self.te_console.setTextCursor(cursor)


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
            # spawn background write
            threading.Thread(target=self._bg_finish_write, daemon=True).start()


    def _bg_finish_write(self):
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        files = write_output_files(
            self.original_lines,
            self.entry_map,
            self.status_map,
            base,
            self.output_dir,
            split=self.split,
            update_quality=self.update_quality,
            update_fps=self.update_fps,
            include_untested=self.include_untested
        )
        for fn in files:
            self.fileWritten.emit(fn)
