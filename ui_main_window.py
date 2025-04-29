import sys
import os
import threading
import queue
from PyQt5 import QtWidgets, QtCore

from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET
from options import OptionsDialog

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # State
        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []
        self.tasks_q = None
        self.threads = []
        self.log_records = []
        self._is_paused = False

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        # Placeholder inputs (managed via OptionsDialog)
        self.le_m3u = QtWidgets.QLineEdit()
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1, 50); self.sp_workers.setValue(5)
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(1, 10); self.sp_retries.setValue(2)
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1, 60); self.sp_timeout.setValue(10)
        self.cb_split = QtWidgets.QCheckBox()
        self.cb_update_quality = QtWidgets.QCheckBox()
        self.cb_update_fps = QtWidgets.QCheckBox()
        self.cb_include_untested = QtWidgets.QCheckBox()
        self.le_out = QtWidgets.QLineEdit(os.getcwd())

        # Buttons
        self.btn_options = QtWidgets.QPushButton("Options")
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_pause = QtWidgets.QPushButton("Pause"); self.btn_pause.setEnabled(False)
        self.btn_stop = QtWidgets.QPushButton("Stop"); self.btn_stop.setEnabled(False)

        # Console and filters
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True)
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info");    self.cb_show_info.setChecked(True)
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error");   self.cb_show_error.setChecked(True)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True)

        # Layout
        central = QtWidgets.QWidget()
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(15)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:32pt;">Don</span>'
            '<span style="font-weight:bold; font-size:32pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:18pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        main_v.addWidget(hdr)

        # Options button
        opt_h = QtWidgets.QHBoxLayout()
        opt_h.addStretch()
        self.btn_options.setFixedSize(120, 40)
        self.btn_options.clicked.connect(self._open_options)
        opt_h.addWidget(self.btn_options)
        opt_h.addStretch()
        main_v.addLayout(opt_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for title in ("Working", "Black Screen", "Non Working"):
            grp = QtWidgets.QGroupBox(title)
            tbl = QtWidgets.QTableWidget(0, 3)
            tbl.setHorizontalHeaderLabels(["Channel","Res","FPS"])
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
            setattr(self, f"tbl_{title.lower().replace(' ', '_')}", tbl)
        main_v.addLayout(panes)

        # Control buttons
        btn_h = QtWidgets.QHBoxLayout()
        btn_h.addStretch()
        for btn in (self.btn_start, self.btn_pause, self.btn_stop):
            btn.setFixedSize(150, 50)
            btn_h.addWidget(btn)
            btn_h.addSpacing(20)
        btn_h.addStretch()
        main_v.addLayout(btn_h)

        # Connect signals
        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_stop.clicked.connect(self.stop_check)

        # Console
        grp_console = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(grp_console)
        filter_h = QtWidgets.QHBoxLayout()
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            filter_h.addWidget(cb)
            cb.stateChanged.connect(self._refresh_console)
        console_v.addLayout(filter_h)
        console_v.addWidget(self.te_console)
        main_v.addWidget(grp_console)

        self.setCentralWidget(central)

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

    def _toggle_pause(self):
        if not self._is_paused:
            for t in self.threads:
                t.pause()
            self.btn_pause.setText("Resume")
            self.status.showMessage("Paused", 3000)
        else:
            for t in self.threads:
                t.resume()
            self.btn_pause.setText("Pause")
            self.status.showMessage("Resumed", 3000)
        self._is_paused = not self._is_paused

    def start_check(self):
        if not self.le_m3u.text() or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "Missing Settings",
                "Please configure options and select groups before starting."
            )
            return
        # Reset
        for key in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{key}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # Parse groups
        gu, cats = parse_groups(self.le_m3u.text())
        self.group_urls = gu
        self.categories = cats
        # Prepare tasks
        q = queue.Queue()
        for grp in self.selected_groups:
            for name, url in self.group_urls.get(grp, []):
                q.put((name, url))
        self.tasks_q = q

        # Start workers
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
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        self.status.showMessage("Stopped", 3000)
        threading.Thread(target=self._on_all_done, daemon=True).start()

    def _on_result(self, name, status, res, br, fps):
        key = {'UP': 'working', 'BLACK_SCREEN': 'black_screen'}.get(status, 'non_working')
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col, txt in enumerate([name, res, fps]):
            tbl.setItem(row, col, QtWidgets.QTableWidgetItem(txt))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        show = {
            'working': self.cb_show_working.isChecked(),
            'info': self.cb_show_info.isChecked(),
            'error': self.cb_show_error.isChecked(),
        }
        self.te_console.clear()
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(m)

    def _on_all_done(self):
        for t in self.threads:
            t.wait()
        # Write M3U outputs if requested
        if self.cb_split.isChecked():
            base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]
            outd = self.le_out.text() or os.getcwd()
            for key, suffix in [
                ('working', '_working'),
                ('black_screen', '_blackscreen'),
                ('non_working', '_notworking'),
            ]:
                fn = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    tbl = getattr(self, f"tbl_{key}")
                    for row in range(tbl.rowCount()):
                        name = tbl.item(row, 0).text()
                        for grp, lst in self.group_urls.items():
                            for nm, url in lst:
                                if nm == name:
                                    f.write(url + '\n')
                                    break
        self.status.showMessage("All tasks complete", 5000)
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_gui()
