import sys
import os
import threading
import queue

from PyQt5 import QtWidgets, QtCore
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET
from utils import clean_name, resolution_to_label, format_fps
from options import OptionsDialog


class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)
        # Option state
        self.m3u_file = ""
        self.group_urls = {}
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
        self.log_records = []
        self._is_paused = False
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

        # Top buttons row
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
        top_h.addStretch()
        main_v.addLayout(top_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ("working", "black_screen", "non_working"):
            title = status.replace('_', ' ').title()
            grp = QtWidgets.QGroupBox(title)
            tbl = QtWidgets.QTableWidget(0, 3)
            tbl.setHorizontalHeaderLabels(["Channel", "Res", "FPS"])
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

        # Console and filters
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
                "Please select an M3U file and at least one group before starting."
            )
            return

        # Print selected groups count to the console
        print(f"Selected {len(self.selected_groups)} groups")

        # Clear previous results
        for status in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{status}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # Prepare task queue
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for entry in self.group_urls.get(grp, []):
                name = entry['name']
                url = entry['url']
                self.tasks_q.put((name, url))

        # Start worker threads
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        self.status.showMessage("Checking started", 3000)

    def _on_result(self, name, status, res, fps):
        key = 'working' if status == 'UP' else ('black_screen' if status == 'BLACK_SCREEN' else 'non_working')
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)
        tbl.setItem(row, 0, QtWidgets.QTableWidgetItem(clean_name(name)))
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
            'info': self.cb_show_info.isChecked(),
            'error': self.cb_show_error.isChecked()
        }
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(m)

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        self.status.showMessage("Paused" if self._is_paused else "Resumed", 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        threading.Thread(target=self._on_all_done, daemon=True).start()

    def _on_all_done(self):
        for t in self.threads:
            t.wait()
        if self.split:
            base = os.path.splitext(os.path.basename(self.m3u_file))[0]
            for status, suffix in [('working', '_working'), ('black_screen', '_blackscreen'), ('non_working', '_notworking')]:
                fn = os.path.join(self.output_dir, f"{base}{suffix}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    tbl = getattr(self, f"tbl_{status}")
                    for row in range(tbl.rowCount()):
                        nm = tbl.item(row, 0).text()
                        for grp, lst in self.group_urls.items():
                            for n, url in lst:
                                if n == nm:
                                    f.write(url + "\n")
                                    break
        self.status.showMessage("All tasks complete", 5000)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_gui()
