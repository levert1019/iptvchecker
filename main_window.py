import sys
import os
import threading
import queue
from PyQt5 import QtWidgets, QtCore

from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET
from utils import QUALITY_LABELS, sup_digits, format_fps, resolution_to_label, clean_name
from options import OptionsDialog

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # --- State ---
        self.group_urls = {}
        self.categories  = {}
        self.selected_groups = []
        self.tasks_q    = None
        self.threads    = []
        self.log_records= []
        self._is_paused = False

        # --- Placeholder storage for options ---
        self.le_m3u            = QtWidgets.QLineEdit()
        self.sp_workers        = QtWidgets.QSpinBox()
        self.sp_retries        = QtWidgets.QSpinBox()
        self.sp_timeout        = QtWidgets.QSpinBox()
        self.cb_split          = QtWidgets.QCheckBox()
        self.cb_update_quality = QtWidgets.QCheckBox()
        self.cb_update_fps     = QtWidgets.QCheckBox()
        self.cb_include_untested = QtWidgets.QCheckBox()
        self.le_out            = QtWidgets.QLineEdit(os.getcwd())

        self._setup_placeholders()
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _setup_placeholders(self):
        self.sp_workers.setRange(1, 100)
        self.sp_workers.setValue(30)
        self.sp_retries.setRange(0, 10)
        self.sp_retries.setValue(3)
        self.sp_timeout.setRange(1, 60)
        self.sp_timeout.setValue(15)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10,10,10,10)
        main_v.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:28pt;">Don</span>'
            '<span style="font-weight:bold; font-size:28pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:16pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        main_v.addWidget(hdr)

        # Top buttons row: Options, Start, Pause, Stop
        top_h = QtWidgets.QHBoxLayout()
        top_h.addStretch()
        buttons = [
            ("Options", self._open_options),
            ("Start",   self.start_check),
            ("Pause",   self._toggle_pause),
            ("Stop",    self.stop_check),
        ]
        for text, slot in buttons:
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
            title = status.replace("_", " ").title()
            grp   = QtWidgets.QGroupBox(title)
            tbl   = QtWidgets.QTableWidget(0, 3)
            tbl.setHorizontalHeaderLabels(["Channel", "Res", "FPS"])
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            tbl.setStyleSheet(
                "QHeaderView::section { background-color: #2b2b2b; color: #e0e0e0; }"
                "QTableWidget { background-color: #3c3f41; color: #e0e0e0; }"
                "QTableWidget::item:selected { background-color: #5b2fc9; color: white; }"
            )
            v = QtWidgets.QVBoxLayout(grp)
            v.addWidget(tbl)
            panes.addWidget(grp)
            setattr(self, f"tbl_{status}", tbl)
        main_v.addLayout(panes)

        # Console & filters
        grp_console = QtWidgets.QGroupBox("Console")
        console_v  = QtWidgets.QVBoxLayout(grp_console)
        filter_h   = QtWidgets.QHBoxLayout()
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
        main_v.addWidget(grp_console)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

    def _open_options(self):
        dlg = OptionsDialog(self)
        # Prefill
        dlg.le_m3u.setText(self.le_m3u.text())
        dlg.sp_workers.setValue(self.sp_workers.value())
        dlg.sp_retries.setValue(self.sp_retries.value())
        dlg.sp_timeout.setValue(self.sp_timeout.value())
        dlg.cb_split.setChecked(self.cb_split.isChecked())
        dlg.cb_update_quality.setChecked(self.cb_update_quality.isChecked())
        dlg.cb_update_fps.setChecked(self.cb_update_fps.isChecked())
        dlg.cb_include_untested.setChecked(self.cb_include_untested.isChecked())
        dlg.le_out.setText(self.le_out.text())
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            # Apply back
            self.le_m3u.setText(dlg.le_m3u.text())
            self.sp_workers.setValue(dlg.sp_workers.value())
            self.sp_retries.setValue(dlg.sp_retries.value())
            self.sp_timeout.setValue(dlg.sp_timeout.value())
            self.cb_split.setChecked(dlg.cb_split.isChecked())
            self.cb_update_quality.setChecked(dlg.cb_update_quality.isChecked())
            self.cb_update_fps.setChecked(dlg.cb_update_fps.isChecked())
            self.cb_include_untested.setChecked(dlg.cb_include_untested.isChecked())
            self.le_out.setText(dlg.le_out.text())

    # Option callbacks
    def _on_browse_m3u(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U Files (*.m3u)"
        )
        if fn:
            self.le_m3u.setText(fn)
            self.group_urls, self.categories = parse_groups(fn)
            self.selected_groups = []

    def _on_select_groups(self):
        dlg = GroupSelectionDialog(self.categories, self.group_urls, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _on_browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Folder"
        )
        if d:
            self.le_out.setText(d)

    # Main control logic
    def start_check(self):
        if not self.le_m3u.text() or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "Missing Settings",
                "Please select an M3U file and at least one group before starting."
            )
            return
        # Clear
        for status in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{status}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # Queue
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for name, url in self.group_urls.get(grp, []):
                self.tasks_q.put((name, url))

        # Threads
        self.threads = []
        for _ in range(self.sp_workers.value()):
            t = WorkerThread(
                self.tasks_q,
                self.sp_retries.value(),
                self.sp_timeout.value()
            )
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        self.status.showMessage("Checking started", 3000)

    def _on_result(self, name, status, res, br, fps):
        key = 'working' if status=='UP' else ('black_screen' if status=='BLACK_SCREEN' else 'non_working')
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)
        display_name = clean_name(name)
        res_label = resolution_to_label(res) if self.cb_update_quality.isChecked() else res
        fps_label = format_fps(fps) if self.cb_update_fps.isChecked() else fps
        tbl.setItem(row, 0, QtWidgets.QTableWidgetItem(display_name))
        tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res_label))
        tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(fps_label))

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
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(m)

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        # Pause button text remains static since Start/Pause now top row
        self.status.showMessage("Paused" if self._is_paused else "Resumed", 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        threading.Thread(target=self._on_all_done, daemon=True).start()

    def _on_all_done(self):
        for t in self.threads:
            t.wait()
        if self.cb_split.isChecked():
            base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]
            outd = self.le_out.text() or os.getcwd()
            for status, suffix in [
                ('working', '_working'),
                ('black_screen', '_blackscreen'),
                ('non_working', '_notworking'),
            ]:
                fn = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    tbl = getattr(self, f"tbl_{status}")
                    for row in range(tbl.rowCount()):
                        nm = tbl.item(row, 0).text()
                        for grp, lst in self.group_urls.items():
                            for n, url in lst:
                                if n == nm:
                                    f.write(url + '\n')
                                    break
        self.status.showMessage("All tasks complete", 5000)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_gui()
