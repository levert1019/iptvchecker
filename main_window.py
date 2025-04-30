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
        self.group_entries = {}
        self.categories = {}

        # UI state
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

        # Runtime
        self.entry_map = {}       # name -> {extinf,name,url}
        self.tasks_q = None
        self.threads = []
        self.log_records = []
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
            '<span style="font-weight:bold; font-size:16pt;"> IPTV Checker</span>')
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        main_v.addWidget(hdr)

        # Buttons
        top_h = QtWidgets.QHBoxLayout()
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
            top_h.addWidget(btn)
            top_h.addSpacing(15)
        main_v.addLayout(top_h)

        # Tables
        pane_h = QtWidgets.QHBoxLayout()
        for status in ("working", "black_screen", "non_working"):
            grp = QtWidgets.QGroupBox(status.replace("_", " ").title())
            if status == "working":
                cols, headers = 3, ["Channel", "Res", "FPS"]
            else:
                cols, headers = 1, ["Channel"]
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            tbl.setStyleSheet(
                "QHeaderView::section { background-color:#2b2b2b; color:#e0e0e0; }"
                "QTableWidget { background-color:#3c3f41; color:#e0e0e0; }"
                "QTableWidget::item:selected { background-color:#5b2fc9; color:white; }"
            )
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            pane_h.addWidget(grp)
            setattr(self, f"tbl_{status}", tbl)
        main_v.addLayout(pane_h)

        # Console
        console_grp = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(console_grp)
        filter_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            filter_h.addWidget(cb)
            cb.stateChanged.connect(self._refresh_console)
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
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.m3u_file       = dlg.le_m3u.text()
            self.selected_groups= dlg.selected_groups
            self.workers        = dlg.sp_workers.value()
            self.retries        = dlg.sp_retries.value()
            self.timeout        = dlg.sp_timeout.value()
            self.split          = dlg.cb_split.isChecked()
            self.update_quality= dlg.cb_update_quality.isChecked()
            self.update_fps    = dlg.cb_update_fps.isChecked()
            self.include_untested = dlg.cb_include_untested.isChecked()
            self.output_dir    = dlg.le_out.text()
            # Parse the new M3U immediately
            self.group_entries, self.categories = parse_groups(self.m3u_file)

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "Missing Settings",
                "Please select an M3U file and at least one group."
            )
            return

        # Clear old
        for s in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()
        self.written.clear()

        # Build full entry_map from every parsed group
        self.entry_map = {
            e['name']: e
            for entries in self.group_entries.values()
            for e in entries
        }

        # Queue tasks for only selected groups
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                self.tasks_q.put((e['name'], e['url']))

        # Log count
        self._on_log('info', f"Selected {len(self.selected_groups)} groups")

        # Launch workers
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # Monitor
        threading.Thread(target=self._monitor_threads, daemon=True).start()
        self.status.showMessage("Checking started", 3000)

    def _on_result(self, name, status, res, fps):
        # choose table
        if status == 'UP':
            key = 'working'
        elif status == 'BLACK_SCREEN':
            key = 'black_screen'
        else:
            key = 'non_working'

        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)

        display = clean_name(name)
        # only on UP do we append quality/fps
        if status == 'UP':
            if self.update_quality:
                display += resolution_to_label(res)
            if self.update_fps:
                display += format_fps(fps)

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, name)
        tbl.setItem(row, 0, item)

        if key == 'working':
            # show res / fps columns
            tbl.setItem(
                row, 1,
                QtWidgets.QTableWidgetItem(
                    resolution_to_label(res) if self.update_quality else res
                )
            )
            tbl.setItem(
                row, 2,
                QtWidgets.QTableWidgetItem(
                    format_fps(fps) if self.update_fps else fps
                )
            )

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show = {
            'working': self.cb_show_working.isChecked(),
            'info':    self.cb_show_info.isChecked(),
            'error':   self.cb_show_error.isChecked()
        }
        colors = {'working': '#00ff00', 'info': '#ffa500', 'error': '#ff0000'}
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(f'<span style="color:{colors[lvl]}">{m}</span>')

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
        if not self.m3u_file:
            return
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        paths = []

        # gather tested names & display map
        tested = set()
        display_map = {}
        for status in ('working', 'black_screen', 'non_working'):
            tbl = getattr(self, f"tbl_{status}")
            for i in range(tbl.rowCount()):
                item = tbl.item(i, 0)
                orig = item.data(QtCore.Qt.UserRole)
                tested.add(orig)
                display_map[orig] = item.text()

        def write_list(fn, names):
            with open(fn, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for orig in names:
                    entry = self.entry_map.get(orig)
                    if not entry:
                        continue
                    if orig in tested:
                        prefix = entry['extinf'].split(',', 1)[0]
                        disp = display_map[orig]
                        f.write(f"{prefix},{disp}\n")
                    else:
                        f.write(entry['extinf'] + "\n")
                    f.write(entry['url'] + "\n")
            paths.append(fn)

        # working always
        working = [self.tbl_working.item(r,0).data(QtCore.Qt.UserRole)
                   for r in range(self.tbl_working.rowCount())]
        write_list(os.path.join(self.output_dir, f"{base}_working.m3u"), working)

        if self.split:
            blacks = [self.tbl_black_screen.item(r,0).data(QtCore.Qt.UserRole)
                      for r in range(self.tbl_black_screen.rowCount())]
            write_list(os.path.join(self.output_dir, f"{base}_blackscreen.m3u"), blacks)

            nonw = [self.tbl_non_working.item(r,0).data(QtCore.Qt.UserRole)
                    for r in range(self.tbl_non_working.rowCount())]
            write_list(os.path.join(self.output_dir, f"{base}_notworking.m3u"), nonw)

        if self.include_untested:
            all_names = list(self.entry_map.keys())
            write_list(os.path.join(self.output_dir, f"{base}_all.m3u"), all_names)

        # back to GUI
        self.written = paths
        QtCore.QTimer.singleShot(0, self._on_files_written)

    def _on_files_written(self):
        for p in self.written:
            self._on_log('info', f"Wrote output file: {p}")
        self._on_log('info', "All tasks complete")
        self.status.showMessage("All tasks complete", 5000)


if __name__ == "__main__":
    run_gui()
