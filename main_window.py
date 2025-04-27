# main_window.py

import sys
import os
import queue
import threading
import re
from PyQt5 import QtWidgets, QtCore

from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET

# Superscript mappings for digits, 'b', 'p', 's'
_SUPER_DIGITS = str.maketrans({
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    'b': 'ᵇ', 'p': 'ᵖ', 's': 'ˢ'
})

# Quality labels in small script
QUALITY_LABELS = {
    'sd': 'ˢᴰ',
    'hd': 'ᴴᴰ',
    'fhd': 'ᶠᴴᴰ',
    'uhd': 'ᵁᴴᴰ'
}


class IPTVChecker(QtWidgets.QMainWindow):
    """Main GUI window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # Parsed entries: group → list of dicts {"extinf","name","url"}
        self.entries: dict[str, list[dict[str, str]]] = {}
        self.categories: dict[str, list[str]] = {}
        self.selected_groups: list[str] = []

        # Runtime data
        self.tasks_q: queue.Queue | None = None
        self.threads: list[WorkerThread] = []
        self.results: dict[str, tuple[str, str, str]] = {}   # name → (res, br, fps)
        self.statuses: dict[str, str] = {}                   # name → status reported by workers
        self.log_records: list[tuple[str, str]] = []         # (level, message)
        self._is_paused: bool = False

        # Build UI & apply stylesheet
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    # ---------------------------------------------------------------------
    # UI construction helpers
    # ---------------------------------------------------------------------

    def _build_ui(self):
        central = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # Header -----------------------------------------------------------
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:32pt;">Don</span>'
            '<span style="font-weight:bold; font-size:32pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:18pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(hdr)

        # File & group selection bar --------------------------------------
        h0 = QtWidgets.QHBoxLayout()
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U")
        btn_browse.clicked.connect(self._on_browse_m3u)
        self.btn_select = QtWidgets.QPushButton("Select Groups")
        self.btn_select.setEnabled(False)
        self.btn_select.clicked.connect(self._on_select_groups)
        h0.addWidget(self.le_m3u)
        h0.addWidget(btn_browse)
        h0.addWidget(self.btn_select)
        v.addLayout(h0)

        # Options bar ------------------------------------------------------
        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(QtWidgets.QLabel("Workers:"))
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1, 50)
        self.sp_workers.setValue(5)
        h1.addWidget(self.sp_workers)

        h1.addWidget(QtWidgets.QLabel("Retries:"))
        self.sp_retries = QtWidgets.QSpinBox()
        self.sp_retries.setRange(1, 10)
        self.sp_retries.setValue(2)
        h1.addWidget(self.sp_retries)

        h1.addWidget(QtWidgets.QLabel("Timeout (s):"))
        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(1, 60)
        self.sp_timeout.setValue(10)
        h1.addWidget(self.sp_timeout)

        self.cb_split = QtWidgets.QCheckBox("Split Output into Files")
        self.cb_update_name = QtWidgets.QCheckBox("Update Name")
        h1.addWidget(self.cb_split)
        h1.addWidget(self.cb_update_name)

        h1.addWidget(QtWidgets.QLabel("Out Folder:"))
        self.le_out = QtWidgets.QLineEdit()
        self.le_out.setPlaceholderText("Select output folder…")
        btn_out = QtWidgets.QPushButton("Browse")
        btn_out.clicked.connect(self._on_browse_out)
        h1.addWidget(self.le_out)
        h1.addWidget(btn_out)
        v.addLayout(h1)

        # Control buttons --------------------------------------------------
        h2 = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_pause.setEnabled(False)
        self.btn_stop = QtWidgets.QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        h2.addWidget(self.btn_start)
        h2.addWidget(self.btn_pause)
        h2.addWidget(self.btn_stop)
        v.addLayout(h2)
        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause.clicked.connect(self._on_pause_resume)
        self.btn_stop.clicked.connect(self.stop_check)

        # Result tables ----------------------------------------------------
        panes = QtWidgets.QHBoxLayout()
        for title in ["Working", "Black Screen", "Non Working"]:
            box = QtWidgets.QGroupBox(title)
            tbl = QtWidgets.QTableWidget(0, 3)
            tbl.setHorizontalHeaderLabels(["Channel", "Res", "FPS"])
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(box).addWidget(tbl)
            panes.addWidget(box)
            setattr(self, f"tbl_{title.lower().replace(' ', '_')}", tbl)
        v.addLayout(panes)

        # Console + filters ------------------------------------------------
        grpC = QtWidgets.QGroupBox("Console")
        vg = QtWidgets.QVBoxLayout(grpC)
        hf = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True)
        self.cb_show_info = QtWidgets.QCheckBox("Show Info"); self.cb_show_info.setChecked(True)
        self.cb_show_error = QtWidgets.QCheckBox("Show Error"); self.cb_show_error.setChecked(True)
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            hf.addWidget(cb)
            cb.stateChanged.connect(self._refresh_console)
        vg.addLayout(hf)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        vg.addWidget(self.te_console)
        v.addWidget(grpC)

        # Finalise ---------------------------------------------------------
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Browse / select helpers
    # ------------------------------------------------------------------

    def _on_browse_m3u(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select M3U File", "", "M3U Files (*.m3u)")
        if not fn:
            return
        self.le_m3u.setText(fn)
        self.entries, self.categories = parse_groups(fn)
        self.btn_select.setEnabled(True)

    def _on_select_groups(self):
        dlg = GroupSelectionDialog(self.categories, self.entries, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected()

    def _on_browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            self.le_out.setText(d)

    # ------------------------------------------------------------------
    # Processing life‑cycle
    # ------------------------------------------------------------------

    def start_check(self):
        if not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "No Groups", "Please select at least one group.")
            return

        # Clear previous run state
        for key in ("working", "black_screen", "non_working"):
            getattr(self, f"tbl_{key}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()
        self.results.clear()
        self.statuses.clear()

        # Prepare task queue
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.entries.get(grp, []):
                self.tasks_q.put((e['name'], e['url']))

        # Spawn workers
        self.threads = []
        for _ in range(self.sp_workers.value()):
            t = WorkerThread(self.tasks_q, self.sp_retries.value(), self.sp_timeout.value())
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.finished.connect(self._on_thread_finished)
            t.start()
            self.threads.append(t)

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def _on_pause_resume(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            if self._is_paused:
                t.pause()
            else:
                t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")

    def stop_check(self):
        for t in self.threads:
            t.stop()

    def _on_thread_finished(self):
        if all(not t.isRunning() for t in self.threads):
            self._finish_up()

    # ------------------------------------------------------------------
    # Results collation & playlist writing
    # ------------------------------------------------------------------

    def _finish_up(self):
        base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]
        outd = self.le_out.text() or os.getcwd()

        # Build output‑file map ------------------------------------------------
        if self.cb_split.isChecked():
            files: dict[str, str] = {
                'working': f"{base}_working.m3u",
                'black_screen': f"{base}_black_screen.m3u",
                'non_working': f"{base}_non_working.m3u",
            }
        else:
            files = {'all': f"{base}.m3u"}

        status_filter = {
            'working': {'UP'},
            'black_screen': {'BLACK_SCREEN'},
            'non_working': {'DOWN'},
            'all': {'UP', 'BLACK_SCREEN', 'DOWN'}
        }

        # Helpers -----------------------------------------------------------
        def superscript(txt: str) -> str:
            return txt.translate(_SUPER_DIGITS)

        def get_quality(res: str) -> str:
            parts = res.split('×')
            try:
                w = int(parts[0])
            except (ValueError, IndexError):
                return ''
            if w >= 3840:
                return QUALITY_LABELS['uhd']
            if w >= 1920:
                return QUALITY_LABELS['fhd']
            if w >= 1280:
                return QUALITY_LABELS['hd']
            return QUALITY_LABELS['sd']

        # Write every requested playlist -----------------------------------
        for key, fnm in files.items():
            fn = os.path.join(outd, fnm)
            with open(fn, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for grp in self.selected_groups:
                    for e in self.entries.get(grp, []):
                        name = e['name']
                        status = self.statuses.get(name, 'DOWN')
                        if status not in status_filter[key]:
                            continue

                        ext = e['extinf']
                        url = e['url']

                        # Optionally update displayed channel name ---------
                        if self.cb_update_name.isChecked():
                            res, br, _ = self.results.get(name, ('–', '–', '–'))
                            new_name = f"{name} {get_quality(res)} {superscript(fps)}ᶠᵖˢ"
                            if ',' in ext:
                                ext = f"{ext.rsplit(',', 1)[0]},{new_name}"
                        f.write(f"{ext}\n{url}\n")

        QtWidgets.QMessageBox.information(self, "Done", f"Wrote {len(files)} playlist(s) to {outd}")
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots for worker signals
    # ------------------------------------------------------------------

    def _on_result(self, name: str, status: str, res: str, br: str, fps: str):
        # Store results for later use in naming
        self.results[name] = (res, br, fps)
        self.statuses[name] = status

        key = {'UP': 'working', 'BLACK_SCREEN': 'black_screen'}.get(status, 'non_working')
        tbl: QtWidgets.QTableWidget = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)
        for col, txt in enumerate([name, res, fps]):
            tbl.setItem(row, col, QtWidgets.QTableWidgetItem(txt))

    def _on_log(self, level: str, msg: str):
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

# ----------------------------------------------------------------------
# Entry‑point
# ----------------------------------------------------------------------

def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
