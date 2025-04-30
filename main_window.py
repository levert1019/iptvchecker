import sys
import os
import threading
import queue
import re

from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog

# Regexes for rewriting EXTINF lines
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

        # Parsed data
        self.group_entries = {}   # group -> list of entry dicts
        self.categories = {}

        # User options
        self.m3u_file = ""
        self.selected_groups = []
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False
        self.output_dir = os.getcwd()

        # Runtime state
        self.entry_map = {}        # uid -> entry dict
        self.tasks_q = None
        self.threads = []
        self.log_records = []      # list of (level, message)
        self._is_paused = False
        self.written = []

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:28pt;">Don</span>'
            '<span style="font-weight:bold; font-size:28pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:16pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        main_v.addWidget(hdr)

        # Top buttons
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
        main_v.addLayout(top_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ('working', 'black_screen', 'non_working'):
            grp = QtWidgets.QGroupBox(status.replace('_', ' ').title())
            if status == 'working':
                cols, hdrs = 3, ['Channel', 'Res', 'FPS']
            else:
                cols, hdrs = 1, ['Channel']
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(hdrs)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            panes.addWidget(grp)
            setattr(self, f"tbl_{status}", tbl)
        main_v.addLayout(panes)

        # Console & filters
        console_grp = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(console_grp)
        filter_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_console)
            filter_h.addWidget(cb)
        console_v.addLayout(filter_h)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)
        main_v.addWidget(console_grp)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _open_options(self):
        dlg = OptionsDialog(self)
        dlg.le_m3u.setText(self.m3u_file)
        dlg.sp_workers.setValue(self.workers)
        dlg.sp_retries.setValue(self.retries)
        dlg.sp_timeout.setValue(self.timeout)
        dlg.cb_split.setChecked(self.split)
        dlg.cb_update_quality.setChecked(self.update_quality)
        dlg.cb_update_fps.setChecked(self.update_fps)
        dlg.cb_include_untested.setChecked(self.include_untested)
        dlg.le_out.setText(self.output_dir)
        # Populate groups if M3U loaded
        if self.m3u_file:
            self.group_entries, self.categories = parse_groups(self.m3u_file)
            dlg.group_urls = self.group_entries
            dlg.categories = self.categories
            dlg.selected_groups = list(self.selected_groups)
            dlg.btn_groups.setEnabled(True)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
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
            self.group_entries, self.categories = parse_groups(self.m3u_file)

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings", "Select an M3U and groups.")
            return
        # Clear UI
        for s in ('working', 'black_screen', 'non_working'):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()
        self.written.clear()
        # Build entry_map by uid
        self.entry_map = {e['uid']: e for grp in self.group_entries.values() for e in grp}
        # Queue entries for testing
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                self.tasks_q.put(e.copy())
        self._on_log('info', f"Selected {len(self.selected_groups)} groups")
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
        uid = entry['uid']
        tbl = self.tbl_working if status == 'UP' else (self.tbl_black_screen if status == 'BLACK_SCREEN' else self.tbl_non_working)
        row = tbl.rowCount()
        tbl.insertRow(row)
        display = clean_name(entry['name'])
        if status == 'UP':
            if self.update_quality:
                q = resolution_to_label(res)
                if q:
                    display += ' ' + q
            if self.update_fps:
                f_lbl = format_fps(fps)
                if f_lbl:
                    display += ' ' + f_lbl
        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)
        if tbl is self.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(fps))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show = {
            'working': self.cb_show_working.isChecked(),
            'info': self.cb_show_info.isChecked(),
            'error': self.cb_show_error.isChecked()
        }
        cols = {'working': '#00ff00', 'info': '#ffa500', 'error': '#ff0000'}
        for lvl, m in self.log_records:
            if show.get(lvl):
                self.te_console.append(f'<span style="color:{cols[lvl]}">{m}</span>')

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            if self._is_paused:
                t.pause()
            else:
                t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed", 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()

    def _monitor_threads(self):
        for t in self.threads:
            t.wait()
        QtCore.QTimer.singleShot(0, self._start_writing)

    def _start_writing(self):
        threading.Thread(target=self._write_output_files, daemon=True).start()

    def _write_output_files(self):
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        paths = []
        # Gather tested UIDs and display names
        tested, disp_map = set(), {}
        for tbl in (self.tbl_working, self.tbl_black_screen, self.tbl_non_working):
            for r in range(tbl.rowCount()):
                uid = tbl.item(r, 0).data(QtCore.Qt.UserRole)
                tested.add(uid)
                disp_map[uid] = tbl.item(r, 0).text()

        def write(fn, uids):
            with open(fn, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U
')
                for uid in uids:
                    ent = self.entry_map[uid]
                    extinf, url = ent['extinf'], ent['url']
                    if uid in tested:
                        extinf = extinf_tvg_re.sub(
                            lambda m: f'{m.group(1)}{disp_map[uid]}{m.group(2)}',
                            extinf
                        )
                        extinf = extinf_comma_re.sub(
                            lambda m: f'{m.group(1)}{disp_map[uid]}',
                            extinf
                        )
                    f.write(extinf + '
')
                    f.write(url + '
')
            paths.append(fn)

        # Write working
        w_uids = [self.tbl_working.item(r, 0).data(QtCore.Qt.UserRole) for r in range(self.tbl_working.rowCount())]
        write(os.path.join(self.output_dir, f"{base}_working.m3u"), w_uids)
        # Split extras
        if self.split:
            b_uids = [self.tbl_black_screen.item(r, 0).data(QtCore.Qt.UserRole) for r in range(self.tbl_black_screen.rowCount())]
            write(os.path.join(self.output_dir, f"{base}_blackscreen.m3u"), b_uids)
            n_uids = [self.tbl_non_working.item(r, 0).data(QtCore.Qt.UserRole) for r in range(self.tbl_non_working.rowCount())]
            write(os.path.join(self.output_dir, f"{base}_notworking.m3u"), n_uids)
        # All channels
        if self.include_untested:
            all_uids = list(self.entry_map.keys())
            write(os.path.join(self.output_dir, f"{base}_all.m3u"), all_uids)

        self.written = paths
        QtCore.QTimer.singleShot(0, self._on_files_written)

    def _on_files_written(self):
        for p in self.written:
            self._on_log('info', f"Wrote output file: {p}")
        self._on_log('info', 'All tasks complete')
        self.status.showMessage('All tasks complete', 5000)

if __name__ == "__main__":
    run_gui()
