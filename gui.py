# gui.py

import sys
import os
import threading
import queue

from PyQt5 import QtWidgets, QtGui, QtCore
from parser import parse_groups
from checker import check_stream

# Theme colors
DEEP_PURPLE = "#5b2fc9"
DARK_BG     = "#2b2b2b"
MID_BG      = "#3c3f41"
TEXT_LIGHT  = "#e0e0e0"
HEADER_FONT = "Arial"

# Shared dark theme stylesheet
STYLE_SHEET = f"""
QWidget {{ background: {DARK_BG}; color: {TEXT_LIGHT}; }}
QLabel, QGroupBox::title {{ color: {TEXT_LIGHT}; }}
QLineEdit {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
QSpinBox, QComboBox {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
QCheckBox {{ color: {TEXT_LIGHT}; }}
QPushButton {{
    background: {DEEP_PURPLE};
    color: white;
    border-radius: 4px;
    padding: 6px;
}}
QPushButton:hover {{ background: #7e52e0; }}
QGroupBox {{
    background: {MID_BG};
    border: 2px solid {DEEP_PURPLE};
    margin-top: 1em;
}}
QGroupBox::title {{
    background-color: {DARK_BG};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px;
}}
QTableWidget, QListWidget {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
QScrollArea {{ background: {DARK_BG}; border: none; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {MID_BG};
    width: 12px; height: 12px;
}}
QScrollBar::handle {{
    background: {DEEP_PURPLE};
    min-height: 20px; border-radius: 6px;
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none;
}}
QTextEdit {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
QStatusBar {{ background: {MID_BG}; color: {TEXT_LIGHT}; }}
"""

class WorkerThread(QtCore.QThread):
    result = QtCore.pyqtSignal(str, str, str, str, str)  # name, status, res, bitrate, fps
    log    = QtCore.pyqtSignal(str, str)                # level, msg

    def __init__(self, tasks: queue.Queue, retries: int, timeout: float):
        super().__init__()
        self.tasks   = tasks
        self.retries = retries
        self.timeout = timeout
        self._pause  = threading.Event()
        self._stop   = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                name, url = self.tasks.get_nowait()
            except queue.Empty:
                break

            # pause handling
            while self._pause.is_set() and not self._stop.is_set():
                self.sleep(1)
                if self._stop.is_set():
                    break

            status, res, br, fps = 'DOWN', '–', '–', '–'
            for attempt in range(1, self.retries + 1):
                self.log.emit('info', f"Testing {name} (try {attempt})")
                st, r, b, f = check_stream(name, url, timeout=self.timeout)
                if st == 'UP':
                    status, res, br, fps = st, r, b, f
                    self.log.emit('working', f"{name} OK [{r}, {f} FPS, {b}]")
                    break
                elif st == 'BLACK_SCREEN':
                    status, res, br, fps = st, r, b, f
                    self.log.emit('error', f"{name} BLACK SCREEN")
                    break
                else:
                    status, res, br, fps = st, r, b, f
                    self.log.emit('error', f"{name} DOWN")

            self.result.emit(name, status, res, br, fps)
            self.log.emit('info', 'Worker thread finished')

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def stop(self):
        self._stop.set()
        self.resume()


class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        self.group_urls      = {}
        self.categories      = {}
        self.selected_groups = []
        self.threads         = []
        self.tasks_q         = None
        self.log_records     = []  # list of (level, message)

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        # Central layout
        win = QtWidgets.QWidget()
        v   = QtWidgets.QVBoxLayout(win)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # Header
        hdr = QtWidgets.QLabel()
        hdr.setText(
            f'<span style="font-family:{HEADER_FONT}; font-weight:bold; font-size:32pt; color:{TEXT_LIGHT};">Don</span>'
            f'<span style="font-family:{HEADER_FONT}; font-weight:bold; font-size:32pt; color:{DEEP_PURPLE};">TV</span>'
            f'<span style="font-family:{HEADER_FONT}; font-weight:bold; font-size:18pt; color:{TEXT_LIGHT};"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(hdr)

        # File & group selection bar
        h0 = QtWidgets.QHBoxLayout()
        self.le_m3u      = QtWidgets.QLineEdit()
        h0.addWidget(self.le_m3u)
        btn_browse       = QtWidgets.QPushButton("Browse M3U")
        h0.addWidget(btn_browse)
        btn_browse.clicked.connect(self._on_browse_m3u)

        self.btn_select  = QtWidgets.QPushButton("Select Groups")
        self.btn_select.setEnabled(False)
        h0.addWidget(self.btn_select)
        self.btn_select.clicked.connect(self._on_select_groups)

        v.addLayout(h0)

        # Parameters bar
        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(QtWidgets.QLabel("Workers:"))
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,50); self.sp_workers.setValue(5)
        h1.addWidget(self.sp_workers)

        h1.addWidget(QtWidgets.QLabel("Retries:"))
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(1,10); self.sp_retries.setValue(2)
        h1.addWidget(self.sp_retries)

        h1.addWidget(QtWidgets.QLabel("Timeout (s):"))
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10)
        h1.addWidget(self.sp_timeout)

        self.cb_split = QtWidgets.QCheckBox("Split Output into Files")
        h1.addWidget(self.cb_split)

        h1.addWidget(QtWidgets.QLabel("Out Folder:"))
        self.le_out = QtWidgets.QLineEdit()
        self.le_out.setPlaceholderText("Select output folder…")
        h1.addWidget(self.le_out)
        btn_out = QtWidgets.QPushButton("Browse")
        h1.addWidget(btn_out)
        btn_out.clicked.connect(self._on_browse_out)

        v.addLayout(h1)

        # Control buttons
        h2 = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start"); h2.addWidget(self.btn_start)
        self.btn_pause = QtWidgets.QPushButton("Pause"); h2.addWidget(self.btn_pause)
        self.btn_stop  = QtWidgets.QPushButton("Stop");  h2.addWidget(self.btn_stop)
        v.addLayout(h2)

        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause.clicked.connect(self.pause_check)
        self.btn_stop.clicked.connect(self.stop_check)

        # Result panes
        panes = QtWidgets.QHBoxLayout()
        for title in ["Working", "Black Screen", "Non Working"]:
            box = QtWidgets.QGroupBox(title)
            tbl = QtWidgets.QTableWidget(0, 5)
            tbl.setHorizontalHeaderLabels(["Channel", "Status", "Res", "Bitrate", "FPS"])
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            lay = QtWidgets.QVBoxLayout(box)
            lay.addWidget(tbl)
            panes.addWidget(box)
            setattr(self, f"tbl_{title.lower().replace(' ', '_')}", tbl)
        v.addLayout(panes)

        # Console + filters
        grpC = QtWidgets.QGroupBox("Console")
        vg   = QtWidgets.QVBoxLayout(grpC)
        hf   = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True)
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info");    self.cb_show_info.setChecked(True)
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error");   self.cb_show_error.setChecked(True)
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            hf.addWidget(cb)
            cb.stateChanged.connect(self._refresh_console)
        vg.addLayout(hf)

        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        vg.addWidget(self.te_console)
        v.addWidget(grpC)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.setCentralWidget(win)

    # ==== UI callbacks ====

    def _on_browse_m3u(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U Files (*.m3u)"
        )
        if fn:
            self.le_m3u.setText(fn)
            gu, cats = parse_groups(fn)
            self.group_urls      = gu
            self.categories      = cats
            self.selected_groups = []
            self.btn_select.setEnabled(True)

    def _on_select_groups(self):
        # pass both categories and full mapping into the dialog
        from qt_helpers import GroupSelectionDialog
        dlg = GroupSelectionDialog(self.categories, self.group_urls, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _on_browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            self.le_out.setText(d)

    # ==== start / pause / stop ====

    def start_check(self):
        if not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self, "No Groups",
                "Please select at least one group before starting."
            )
            return

        # clear previous results
        for key in ("working", "black_screen", "non_working"):
            tbl = getattr(self, f"tbl_{key}")
            tbl.setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # prepare tasks
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for name, url in self.group_urls.get(grp, []):
                self.tasks_q.put((name, url))

        # spawn workers
        self.threads = []
        for _ in range(self.sp_workers.value()):
            t = WorkerThread(self.tasks_q, self.sp_retries.value(), self.sp_timeout.value())
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        self.status.showMessage("Checking started", 3000)
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def pause_check(self):
        for t in self.threads:
            t.pause()
        QtWidgets.QMessageBox.information(
            self, "Checking Paused",
            "Checking paused, please wait a few seconds…"
        )
        self.status.showMessage("Paused", 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        QtWidgets.QMessageBox.information(
            self, "Checking Stopped",
            "Checking stopped, please wait a few seconds…"
        )
        self.status.showMessage("Stopped", 3000)
        threading.Thread(target=self._on_all_done, daemon=True).start()

    def _on_result(self, name, status, res, br, fps):
        key = {'UP': 'working', 'BLACK_SCREEN': 'black_screen'}.get(status, 'non_working')
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col, txt in enumerate([name, status, res, br, fps]):
            tbl.setItem(row, col, QtWidgets.QTableWidgetItem(txt))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        show = {
            'working':     self.cb_show_working.isChecked(),
            'info':        self.cb_show_info.isChecked(),
            'error':       self.cb_show_error.isChecked(),
        }
        self.te_console.clear()
        for lvl, m in self.log_records:
            if not show.get(lvl, False):
                continue
            self.te_console.append(m)

    def _on_all_done(self):
        for t in self.threads:
            t.wait()

        if self.cb_split.isChecked():
            base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]
            outd = self.le_out.text() or os.getcwd()
            for key, suffix in [
                ('working','_working'),
                ('black_screen','_blackscreen'),
                ('non_working','_notworking')
            ]:
                fn = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    for row in range(getattr(self, f"tbl_{key}").rowCount()):
                        # retrieve channel name from the table
                        name = getattr(self, f"tbl_{key}").item(row, 0).text()
                        # find its URL and write
                        for grp, lst in self.group_urls.items():
                            for nm, url in lst:
                                if nm == name:
                                    f.write(url + '\n')
                                    break
                self.status.showMessage(f"Wrote {fn}", 5000)

        self.status.showMessage("All tasks complete", 5000)
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
