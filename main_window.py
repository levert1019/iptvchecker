import sys
import os
import queue
import threading
import re
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog

# Regex to extract CUID from an EXTINF line
CUID_RE = re.compile(r'CUID="([^"]+)"')

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # --- Core state ---
        self.m3u_file = ""
        self.original_lines = []
        self.group_entries = {}       # group_title -> list of entry dicts
        self.categories    = {}       # same shape, for OptionsDialog
        self.selected_groups = []

        # --- Options ---
        self.workers          = 5
        self.retries          = 2
        self.timeout          = 10
        self.split            = False
        self.update_quality   = False
        self.update_fps       = False
        self.include_untested = False
        self.output_dir       = os.getcwd()

        # --- Runtime ---
        self.entry_map   = {}        # uid -> entry dict
        self.threads     = []        # WorkerThread instances
        self.log_records = []        # list of (level, msg)
        self._is_paused  = False
        self._poll_timer = None

        # Build UI
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

        # Controls row
        ctrl_h = QtWidgets.QHBoxLayout()
        for text, slot in [
            ("Options", self._open_options),
            ("Start",   self.start_check),
            ("Pause",   self._toggle_pause),
            ("Stop",    self.stop_check),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(130, 45)
            btn.clicked.connect(slot)
            if text == "Pause":
                self.btn_pause = btn
            ctrl_h.addWidget(btn)
            ctrl_h.addSpacing(10)
        ctrl_h.addStretch()
        main_v.addLayout(ctrl_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ('working', 'black_screen', 'non_working'):
            grp = QtWidgets.QGroupBox(status.replace('_', ' ').title())
            cols = 3 if status == 'working' else 1
            headers = ['Channel', 'Res', 'FPS'] if status == 'working' else ['Channel']
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            panes.addWidget(grp)
        main_v.addLayout(panes)

        # Console + filters
        console_grp = QtWidgets.QGroupBox("Console")
        console_v   = QtWidgets.QVBoxLayout(console_grp)
        flt_h       = QtWidgets.QHBoxLayout()
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
        main_v.addWidget(console_grp)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _open_options(self):
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        # Prefill dialog with current settings
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
            dlg.group_urls    = self.group_entries
            dlg.categories    = self.categories
            dlg.selected_groups = list(self.selected_groups)
            dlg.btn_groups.setEnabled(True)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            opts = dlg.get_options()
            self.m3u_file         = opts['m3u_file']
            self.workers          = opts['workers']
            self.retries          = opts['retries']
            self.timeout          = opts['timeout']
            self.split            = opts['split']
            self.update_quality   = opts['update_quality']
            self.update_fps       = opts['update_fps']
            self.include_untested = opts['include_untested']
            self.output_dir       = opts['output_dir']
            self.selected_groups  = opts['selected_groups']

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "Missing Settings",
                "Please select an M3U file and at least one group."
            )
            return

        # Preserve original M3U lines
        with open(self.m3u_file, 'r', encoding='utf-8') as f:
            self.original_lines = f.readlines()

        # Parse playlist
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        # Clear UI
        for s in ('working', 'black_screen', 'non_working'):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # Build entry map & task queue
        self.entry_map = {e['uid']: e for grp in self.group_entries.values() for e in grp}
        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                q.put(e.copy())
        self.tasks_q = q
        self.status.showMessage(f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups", 3000)

        # Spawn workers
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # Poll for completion
        if not self._poll_timer:
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._monitor_threads)
        self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        tbl = {
            'UP':            self.tbl_working,
            'BLACK_SCREEN':  self.tbl_black_screen
        }.get(status, self.tbl_non_working)

        row = tbl.rowCount()
        tbl.insertRow(row)

        display = clean_name(entry['name'])
        if status == 'UP':
            if self.update_quality:
                q = resolution_to_label(res)
                if q:
                    display += ' ' + q
            if self.update_fps:
                f = format_fps(fps)
                if f:
                    display += ' ' + f

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, entry['uid'])
        tbl.setItem(row, 0, item)

        if tbl is self.tbl_working:
            tbl.setItem(row,1,QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row,2,QtWidgets.QTableWidgetItem(str(fps)))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show = {
            'working': self.cb_show_working.isChecked(),
            'info':    self.cb_show_info.isChecked(),
            'error':   self.cb_show_error.isChecked(),
        }
        colors = {'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(f"<span style='color:{colors[lvl]}'>{m}</span>")

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
        if not self.m3u_file:
            return

        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        outd = self.output_dir or os.getcwd()

        if self.split:
            # your existing split logic here
            pass
        else:
            out = os.path.join(outd, f"{base}_all.m3u")
            with open(out, 'w', encoding='utf-8') as f:
                i = 0
                while i < len(self.original_lines):
                    ln = self.original_lines[i]
                    if ln.startswith("#EXTINF") and (m := CUID_RE.search(ln)):
                        uid = m.group(1)
                        e = self.entry_map.get(uid)
                        if e:
                            attrs = []
                            for k in ('CUID','tvg-name','tvg-id','tvg-logo','group-title'):
                                if k in e:
                                    attrs.append(f'{k}="{e[k]}"')
                            new_ext = "#EXTINF:0 " + " ".join(attrs) + "," + e['name'] + "\n"
                            f.write(new_ext)
                            if i+1 < len(self.original_lines):
                                f.write(self.original_lines[i+1])
                                i += 2
                                continue
                    f.write(ln)
                    i += 1
            self.status.showMessage(f"Wrote {out}", 3000)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
