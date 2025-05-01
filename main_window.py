# main_window.py

import sys
import os
import threading
import queue
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog

# Regexes for rewriting EXTINF lines (if you need to preserve attributes in M3U)
import re
extinf_tvg_re = re.compile(r'(tvg-name=")[^"]*(")')
extinf_comma_re = re.compile(r'^(.*?,)(.*)$')

def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # Data structures
        self.group_entries = {}    # group_title -> list of entry dicts
        self.categories = {}       # same shape, for OptionsDialog
        self.selected_groups = []
        self.m3u_file = ""
        # Options
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False
        self.output_dir = os.getcwd()
        # Runtime
        self.entry_map = {}        # uid -> entry dict
        self.tasks_q = None
        self.threads = []
        self.log_records = []      # list of (level, msg)
        self._is_paused = False
        self.written = []

        # Build UI and apply stylesheet
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(0, 0, 0, 0)
        main_v.setSpacing(0)

        # --- Script switcher bar ---
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #5b2fc9;")
        bar_layout = QtWidgets.QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 0, 0, 0)
        # IPTV Checker tab
        self.btn_script_iptv = QtWidgets.QPushButton("IPTV Checker")
        self.btn_script_iptv.setCheckable(True)
        self.btn_script_iptv.setChecked(True)
        self.btn_script_iptv.setStyleSheet(
            "color: white; background: transparent; font-weight: bold; border: none;"
        )
        self.btn_script_iptv.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        bar_layout.addWidget(self.btn_script_iptv)
        bar_layout.addStretch()
        main_v.addWidget(bar)

        # --- Stacked pages container ---
        self.pages = QtWidgets.QStackedWidget()
        main_v.addWidget(self.pages)

        # --- Page 0: IPTV Checker ---
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(10, 10, 10, 10)
        page_layout.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:28pt;">Don</span>'
            '<span style="font-weight:bold; font-size:28pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:16pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        page_layout.addWidget(hdr)

        # Top buttons: Options, Start, Pause, Stop
        top_h = QtWidgets.QHBoxLayout()
        for text, slot in [
            ("Options", self._open_options),
            ("Start", self.start_check),
            ("Pause", self._toggle_pause),
            ("Stop", self.stop_check),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(130, 45)
            btn.clicked.connect(slot)
            if text == "Pause":
                self.btn_pause = btn
            top_h.addWidget(btn)
            top_h.addSpacing(10)
        top_h.addStretch()
        page_layout.addLayout(top_h)

        # Result tables: Working, Black Screen, Non Working
        panes = QtWidgets.QHBoxLayout()
        for status in ('working', 'black_screen', 'non_working'):
            grp_box = QtWidgets.QGroupBox(status.replace('_', ' ').title())
            cols = 3 if status == 'working' else 1
            headers = ['Channel', 'Res', 'FPS'] if status == 'working' else ['Channel']
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(grp_box).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            panes.addWidget(grp_box)
        page_layout.addLayout(panes)

        # Console + filters
        console_grp = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(console_grp)
        filter_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_console)
            filter_h.addWidget(cb)
        console_v.addLayout(filter_h)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)
        page_layout.addWidget(console_grp)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

        # Add this page to stack
        self.pages.addWidget(page)

    def _open_options(self):
        dlg = OptionsDialog(self)
        # Pre-fill dialog with current settings
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
            # Re-parse groups and pass into dialog
            self.group_entries, self.categories = parse_groups(self.m3u_file)
            dlg.group_urls = self.group_entries
            dlg.categories = self.categories
            dlg.selected_groups = list(self.selected_groups)
            dlg.btn_groups.setEnabled(True)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            # Retrieve updated settings
            self.m3u_file = dlg.le_m3u.text()
            self.selected_groups = dlg.selected_groups
            self.workers = dlg.sp_workers.value()
            self.retries = dlg.sp_retries.value()
            self.timeout = dlg.sp_timeout.value()
            self.split = dlg.cb_split.isChecked()
            self.update_quality = dlg.cb_update_quality.isChecked()
            self.update_fps = dlg.cb_update_fps.isChecked()
            self.include_untested = dlg.cb_include_untested.isChecked()
            self.output_dir = dlg.le_out.text()
            # Re-parse for main logic
            self.group_entries, self.categories = parse_groups(self.m3u_file)

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings", "Please select an M3U file and at least one group.")
            return

        # Clear tables & console
        for s in ('working','black_screen','non_working'):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()
        self.written.clear()

        # Build entry_map for quick lookup
        self.entry_map = {e['uid']: e for grp in self.group_entries.values() for e in grp}

        # Queue tasks
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                self.tasks_q.put(e.copy())

        self._on_log('info', f"Starting check: {len(self.selected_groups)} groups → {self.tasks_q.qsize()} tasks")

        # Spawn workers
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        threading.Thread(target=self._monitor_threads, daemon=True).start()
        self.status.showMessage("Checking started", 3000)

    def _on_result(self, entry, status, res, fps):
        tbl = {
            'UP': self.tbl_working,
            'BLACK_SCREEN': self.tbl_black_screen
        }.get(status, self.tbl_non_working)
        row = tbl.rowCount()
        tbl.insertRow(row)

        # Display name + optional tags
        display = clean_name(entry['name'])
        if status == 'UP':
            if self.update_quality:
                qlbl = resolution_to_label(res)
                if qlbl:
                    display += ' ' + qlbl
            if self.update_fps:
                f_lbl = format_fps(fps)
                if f_lbl:
                    display += ' ' + f_lbl

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, entry['uid'])
        tbl.setItem(row, 0, item)

        if tbl is self.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(fps))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show_map = {
            'working': self.cb_show_working.isChecked(),
            'info':    self.cb_show_info.isChecked(),
            'error':   self.cb_show_error.isChecked(),
        }
        color = {'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for lvl, m in self.log_records:
            if show_map.get(lvl, False):
                self.te_console.append(f"<span style='color:{color[lvl]}'>{m}</span>")

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
        for t in self.threads:
            t.wait()
        QtCore.QTimer.singleShot(0, self._start_writing)

    def _start_writing(self):
        threading.Thread(target=self._write_output_files, daemon=True).start()

    def _write_output_files(self):
        if not self.m3u_file:
            return

        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        outd = self.output_dir or os.getcwd()

        # Build separate files if requested
        if self.split:
            for key, suffix in [
                ('working', '_working'),
                ('black_screen', '_blackscreen'),
                ('non_working', '_notworking'),
            ]:
                fn = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    # iterate rows in the corresponding table
                    tbl = getattr(self, f"tbl_{key}")
                    for row in range(tbl.rowCount()):
                        uid = tbl.item(row, 0).data(QtCore.Qt.UserRole)
                        url = self.entry_map[uid]['url']
                        f.write(url + "\n")
                self.status.showMessage(f"Wrote {fn}", 3000)
        else:
            # Single file: include all categories
            fn = os.path.join(outd, f"{base}_all.m3u")
            with open(fn, 'w', encoding='utf-8') as f:
                for tbl_name in ('working', 'black_screen', 'non_working'):
                    tbl = getattr(self, f"tbl_{tbl_name}")
                    for row in range(tbl.rowCount()):
                        uid = tbl.item(row, 0).data(QtCore.Qt.UserRole)
                        url = self.entry_map[uid]['url']
                        f.write(url + "\n")
            self.status.showMessage(f"Wrote {fn}", 3000)

        self.status.showMessage("All tasks complete", 5000)

if __name__ == "__main__":
    run_gui()
