import sys
import os
import threading
import queue

from PyQt5 import QtWidgets, QtCore
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

        # Option state
        self.m3u_file = ""
        self.group_urls = {}      # group_name -> list of entries
        self.categories = {}
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
        self.tasks_q = None
        self.threads = []
        self.log_records = []     # [(level, message), ...]
        self._is_paused = False
        self.written = []         # list of files written
        self.entry_map = {}       # name -> entry dict

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
        top_h.addStretch()
        for text, slot in [
            ("Options", self._open_options),
            ("Start", self.start_check),
            ("Pause", self._toggle_pause),
            ("Stop", self.stop_check),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(130, 45)
            btn.clicked.connect(slot)
            top_h.addWidget(btn)
            top_h.addSpacing(15)
            if text == "Pause":
                self.btn_pause = btn
        top_h.addStretch()
        main_v.addLayout(top_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ("working", "black_screen", "non_working"):
            grp = QtWidgets.QGroupBox(status.replace('_', ' ').title())
            # Columns and headers per status
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
                "QHeaderView::section { background-color: #2b2b2b; color: #e0e0e0; }"
                "QTableWidget { background-color: #3c3f41; color: #e0e0e0; }"
                "QTableWidget::item:selected { background-color: #5b2fc9; color: white; }"
            )
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            panes.addWidget(grp)
            setattr(self, f"tbl_{status}", tbl)
        main_v.addLayout(panes)

        # Console & filters
        grp_console = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(grp_console)
        filter_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            filter_h.addWidget(cb)
            cb.stateChanged.connect(self._refresh_console)
        console_v.addLayout(filter_h)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)
        main_v.addWidget(grp_console)

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
            self.m3u_file = dlg.le_m3u.text()
            self.group_urls = dlg.group_urls
            self.categories = dlg.categories
            self.selected_groups = dlg.selected_groups
            self.workers = dlg.sp_workers.value()
            self.retries = dlg.sp_retries.value()
            self.timeout = dlg.sp_timeout.value()
            self.split = dlg.cb_split.isChecked()
            self.update_quality = dlg.cb_update_quality.isChecked()
            self.update_fps = dlg.cb_update_fps.isChecked()
            self.include_untested = dlg.cb_include_untested.isChecked()
            self.output_dir = dlg.le_out.text()

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "Missing Settings",
                "Select an M3U file and at least one group before starting."
            )
            return

        # Clear tables and logs
        for status in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{status}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()
        self.written.clear()

        # Build entry map
        self.entry_map = {e['name']: e for entries in self.group_urls.values() for e in entries}
           # Log selected count
        self._on_log('info', f"Selected {len(self.selected_groups)} groups")

        # Queue tasks
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for entry in self.group_urls.get(grp, []):
                self.tasks_q.put((entry['name'], entry['url']))

        # Start workers
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # Monitor completion
        threading.Thread(target=self._monitor_threads, daemon=True).start()
        self.status.showMessage("Checking started", 3000)

def _on_result(self, name, status, res, fps):
    # Determine which table to use
    if status == 'UP':
        key = 'working'
    elif status == 'BLACK_SCREEN':
        key = 'black_screen'
    else:
        key = 'non_working'

    tbl = getattr(self, f"tbl_{key}")
    row = tbl.rowCount()
    tbl.insertRow(row)

    # Base display name
    display = clean_name(name)

    # Only for streams that came up successfully do we append quality/FPS
    if status == 'UP':
        if self.update_quality:
            display += resolution_to_label(res)
        if self.update_fps:
            display += format_fps(fps)

    # Store original name in UserRole for later lookups
    item = QtWidgets.QTableWidgetItem(display)
    item.setData(QtCore.Qt.UserRole, name)
    tbl.setItem(row, 0, item)

    # Populate Res and FPS columns only in the working table
    if key == 'working':
        # Column 1: resolution (or raw res if not injecting)
        tbl.setItem(
            row, 1,
            QtWidgets.QTableWidgetItem(
                resolution_to_label(res) if self.update_quality else res
            )
        )
        # Column 2: fps (or raw fps if not injecting)
        tbl.setItem(
            row, 2,
            QtWidgets.QTableWidgetItem(
                format_fps(fps) if self.update_fps else fps
            )
        )

    def _on_log(self, level, message):
        self.log_records.append((level, message))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show = {'working': self.cb_show_working.isChecked(), 'info': self.cb_show_info.isChecked(), 'error': self.cb_show_error.isChecked()}
        colors = {'working': '#00ff00', 'info': '#ffa500', 'error': '#ff0000'}
        for lvl, msg in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(f'<span style="color:{colors[lvl]}">{msg}</span>')

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed", 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()

    def _monitor_threads(self):
        for t in self.threads:
            t.wait()
        QtCore.QTimer.singleShot(0, self._start_writing)

    def _write_output_files(self):
        if not self.m3u_file:
            return
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        paths = []

        # Gather tested channels and their display names
        tested = set()
        display_map = {}
        for status in ('working', 'black_screen', 'non_working'):
            tbl = getattr(self, f"tbl_{status}")
            for row in range(tbl.rowCount()):
                item = tbl.item(row, 0)
                orig = item.data(QtCore.Qt.UserRole)
                tested.add(orig)
                display_map[orig] = item.text()

        def write_list(path, names):
            with open(path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for orig in names:
                    entry = self.entry_map.get(orig)
                    if not entry:
                        continue
                    if orig in tested:
                        # Rebuild EXTINF using updated display name
                        prefix = entry['extinf'].split(',', 1)[0]
                        disp = display_map[orig]
                        f.write(f"{prefix},{disp}\n")
                    else:
                        # Untested or unselected: write original EXTINF
                        f.write(entry['extinf'] + "\n")
                    f.write(entry['url'] + "\n")
            paths.append(path)

        # 1) Always write working list
        working = [
            self.tbl_working.item(r, 0).data(QtCore.Qt.UserRole)
            for r in range(self.tbl_working.rowCount())
        ]
        write_list(os.path.join(self.output_dir, f"{base}_working.m3u"), working)

        # 2) If splitting, write black_screen & non_working
        if self.split:
            blacks = [
                self.tbl_black_screen.item(r, 0).data(QtCore.Qt.UserRole)
                for r in range(self.tbl_black_screen.rowCount())
            ]
            write_list(os.path.join(self.output_dir, f"{base}_blackscreen.m3u"), blacks)

            nonw = [
                self.tbl_non_working.item(r, 0).data(QtCore.Qt.UserRole)
                for r in range(self.tbl_non_working.rowCount())
            ]
            write_list(os.path.join(self.output_dir, f"{base}_notworking.m3u"), nonw)

        # 3) If include_untested, write the “all” file from every entry
        if self.include_untested:
            all_names = list(self.entry_map.keys())
            write_list(os.path.join(self.output_dir, f"{base}_all.m3u"), all_names)

        # Finally, notify GUI thread
        self.written = paths
        QtCore.QTimer.singleShot(0, self._on_files_written)


    def _on_files_written(self):
        for p in self.written:
            self._on_log('info', f"Wrote output file: {p}")
        self._on_log('info', "All tasks complete")
        self.status.showMessage("All tasks complete", 5000)


if __name__ == "__main__":
    run_gui()
