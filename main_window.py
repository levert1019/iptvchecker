import sys
import os
import re
import queue
import threading
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET

# Superscript quality labels
QUALITY_LABELS = {
    'sd': 'ˢᴰ',
    'hd': 'ᴴᴰ',
    'fhd': 'ᶠᴴᴰ',
    'uhd': 'ᵁᴴᴰ'
}

# Convert digits to superscript
def sup_digits(text: str) -> str:
    tbl = str.maketrans({
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
    })
    return text.translate(tbl)

# Format fps: extract numeric, drop '/1' or '.0', superscript + 'ᶠᵖˢ'
def format_fps(text: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return '–'
    num = m.group(1)
    if num.endswith('.0'):
        num = num[:-2]
    return f"{sup_digits(num)}ᶠᵖˢ"

# Map resolution to quality label
def resolution_to_label(res: str) -> str:
    parts = res.split('×')
    if len(parts) != 2:
        return ''
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        return ''
    if w >= 3840 or h >= 2160:
        key = 'uhd'
    elif w >= 1920 or h >= 1080:
        key = 'fhd'
    elif w >= 1280 or h >= 720:
        key = 'hd'
    else:
        key = 'sd'
    return QUALITY_LABELS[key]

# Remove existing quality/fps in name
def clean_name(name: str) -> str:
    # remove superscript fps
    name = re.sub(r"\d+ᶠᵖˢ", '', name)
    # remove superscript quality labels
    for v in QUALITY_LABELS.values():
        name = name.replace(v, '')
    # remove plaintext markers
    name = re.sub(r"\b(sd|hd|fhd|uhd)\b", '', name, flags=re.IGNORECASE)
    name = re.sub(r"\b\d+(?:\.\d+)?fps\b", '', name, flags=re.IGNORECASE)
    return name.strip()

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)
        # Data
        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []
        # Runtime
        self.tasks_q = None
        self.threads = []
        self.log_records = []
        self.remaining_threads = 0
        self._is_paused = False
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:32pt;">Don</span>'
            '<span style="font-weight:bold; font-size:32pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:18pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(hdr)

        # M3U & group selection
        h0 = QtWidgets.QHBoxLayout()
        self.le_m3u = QtWidgets.QLineEdit(); h0.addWidget(self.le_m3u)
        btn_browse = QtWidgets.QPushButton("Browse M3U"); btn_browse.clicked.connect(self._on_browse_m3u); h0.addWidget(btn_browse)
        self.btn_select = QtWidgets.QPushButton("Select Groups"); self.btn_select.setEnabled(False); self.btn_select.clicked.connect(self._on_select_groups); h0.addWidget(self.btn_select)
        v.addLayout(h0)

        # Options bar
        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(QtWidgets.QLabel("Workers:"))
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,50); self.sp_workers.setValue(5); h1.addWidget(self.sp_workers)
        h1.addWidget(QtWidgets.QLabel("Retries:"))
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(1,10); self.sp_retries.setValue(2); h1.addWidget(self.sp_retries)
        h1.addWidget(QtWidgets.QLabel("Timeout (s):"))
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10); h1.addWidget(self.sp_timeout)
        self.cb_split = QtWidgets.QCheckBox("Split into Files"); h1.addWidget(self.cb_split)
        self.cb_update_name = QtWidgets.QCheckBox("Update Quality in Name"); h1.addWidget(self.cb_update_name)
        h1.addWidget(QtWidgets.QLabel("Out Folder:"))
        self.le_out = QtWidgets.QLineEdit(); self.le_out.setPlaceholderText("Select output folder…"); h1.addWidget(self.le_out)
        btn_out = QtWidgets.QPushButton("Browse"); btn_out.clicked.connect(self._on_browse_out); h1.addWidget(btn_out)
        v.addLayout(h1)

        # Controls
        h2 = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start"); h2.addWidget(self.btn_start)
        self.btn_pause = QtWidgets.QPushButton("Pause"); self.btn_pause.setEnabled(False); h2.addWidget(self.btn_pause)
        self.btn_stop = QtWidgets.QPushButton("Stop"); self.btn_stop.setEnabled(False); h2.addWidget(self.btn_stop)
        v.addLayout(h2)
        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_stop.clicked.connect(self.stop_check)

        # Results tables
        panes = QtWidgets.QHBoxLayout()
        for t in ["Working","Black Screen","Non Working"]:
            box = QtWidgets.QGroupBox(t)
            tbl = QtWidgets.QTableWidget(0,3)
            tbl.setHorizontalHeaderLabels(["Channel","Res","FPS"])
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setStyleSheet(
                "QHeaderView::section { background-color: #2b2b2b; color: #e0e0e0; }"
                "QTableWidget { background-color: #3c3f41; color: #e0e0e0; }"
                "QTableWidget::item:selected { background-color: #5b2fc9; color: white; }"
            )
            QtWidgets.QVBoxLayout(box).addWidget(tbl)
            panes.addWidget(box)
            setattr(self, f"tbl_{t.lower().replace(' ','_')}", tbl)
        v.addLayout(panes)

        # Console filters
        grpC = QtWidgets.QGroupBox("Console")
        vg = QtWidgets.QVBoxLayout(grpC)
        hf2 = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True); hf2.addWidget(self.cb_show_working)
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info");    self.cb_show_info.setChecked(True);    hf2.addWidget(self.cb_show_info)
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error");   self.cb_show_error.setChecked(True);   hf2.addWidget(self.cb_show_error)
        for cb in (self.cb_show_working,self.cb_show_info,self.cb_show_error): cb.stateChanged.connect(self._refresh_console)
        vg.addLayout(hf2)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True); vg.addWidget(self.te_console)
        v.addWidget(grpC)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.setCentralWidget(central)

    def _on_browse_m3u(self):
        fn,_ = QtWidgets.QFileDialog.getOpenFileName(self, "Select M3U File", "", "M3U Files (*.m3u)")
        if fn:
            self.le_m3u.setText(fn)
            self.group_urls, self.categories = parse_groups(fn)
            self.selected_groups = []
            self.btn_select.setEnabled(True)

    def _on_select_groups(self):
        dlg = GroupSelectionDialog(self.categories, self.group_urls, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _on_browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            self.le_out.setText(d)

    def start_check(self):
        if not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "No Groups", "Please select at least one group.")
            return
        for k in ("working","black_screen","non_working"): getattr(self, f"tbl_{k}").setRowCount(0)
        self.log_records.clear(); self.te_console.clear()
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for ent in self.group_urls.get(grp, []):
                self.tasks_q.put((ent['name'], ent['url']))
        self.threads = []
        self.remaining_threads = self.sp_workers.value()
        for _ in range(self.sp_workers.value()):
            t = WorkerThread(self.tasks_q, self.sp_retries.value(), self.sp_timeout.value())
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.finished.connect(self._thread_finished)
            t.start()
            self.threads.append(t)
        self.status.showMessage("Checking started", 3000)
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def _thread_finished(self):
        self.remaining_threads -= 1
        if self.remaining_threads == 0:
            self._on_all_done()

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            (t.pause() if self._is_paused else t.resume())
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        state = "Paused" if self._is_paused else "Resumed"
        QtWidgets.QMessageBox.information(self, f"Checking {state}", f"Checking {state.lower()}…")
        self.status.showMessage(state, 3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        QtWidgets.QMessageBox.information(self, "Checking Stopped", "Checking stopped.")
        self.status.showMessage("Stopped", 3000)
        threading.Thread(target=self._on_all_done, daemon=True).start()

    def _on_result(self, name, status, res, fps):
        key = {'UP':'working', 'BLACK_SCREEN':'black_screen'}.get(status, 'non_working')
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount()
        tbl.insertRow(row)

        # Initialize formatted from original name
        formatted = name
        formatted = re.sub(r"\b(sd|hd|fhd|uhd)\b", lambda m: QUALITY_LABELS[m.group(1).lower()], formatted, flags=re.IGNORECASE)
        formatted = re.sub(r"(\d+(?:/\d+)?)bp?s?", lambda m: format_fps(m.group(0)), formatted, flags=re.IGNORECASE)

        if self.cb_update_name.isChecked():
            base = clean_name(formatted)
            qual_lbl = resolution_to_label(res)
            fps_sup = format_fps(fps)
            display_name = f"{base} {qual_lbl} {fps_sup}".strip()
        else:
            display_name = formatted

        # Table FPS: plain number
        m_f = re.search(r"(\d+(?:\.\d+)?)", fps or "")
        fps_num = m_f.group(1) if m_f else ''
        if fps_num.endswith('.0'):
            fps_num = fps_num[:-2]
        display_fps = fps_num or '–'

        for col, val in enumerate([display_name, res, display_fps]):
            tbl.setItem(row, col, QtWidgets.QTableWidgetItem(val))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        show = {'working':self.cb_show_working.isChecked(), 'info':self.cb_show_info.isChecked(), 'error':self.cb_show_error.isChecked()}
        self.te_console.clear()
        cmap = {'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for lvl, raw in self.log_records:
            if not show.get(lvl): continue
            parts = raw.split('[', 1)
            pref = parts[0].strip()
            pref = re.sub(r"\b(sd|hd|fhd|uhd)\b", lambda m: QUALITY_LABELS[m.group(1).lower()], pref, flags=re.IGNORECASE)
            pref = re.sub(r"(\d+(?:/\d+)?)bp?s?", lambda m: format_fps(m.group(0)), pref, flags=re.IGNORECASE)
            disp = pref
            if len(parts) > 1:
                inner = parts[1].rstrip(']')
                rstr, fps_part = inner.split(',', 1)
                if self.cb_update_name.isChecked():
                    cn = clean_name(pref)
                    lbl = resolution_to_label(rstr.strip())
                    fs = format_fps(fps_part)
                    disp = f"{cn} {lbl} {fs}".strip()
                else:
                    fs = format_fps(fps_part)
                    disp = f"{pref} [{rstr.strip()}, {fs}]"
            self.te_console.append(f'<span style="color:{cmap[lvl]}">{disp}</span>')

    def _on_all_done(self):
        # write m3u outputs if needed
        if self.cb_split.isChecked():
            base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]
            outd = self.le_out.text() or os.getcwd()
            for key, sfx in [('working','_working'),('black_screen','_blackscreen'),('non_working','_notworking')]:
                fn = os.path.join(outd, f"{base}{sfx}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    tbl = getattr(self, f"tbl_{key}")
                    for r in range(tbl.rowCount()):
                        nm = tbl.item(r, 0).text()
                        for lst in self.group_urls.values():
                            for ent in lst:
                                if ent.get('name') == nm:
                                    f.write(ent.get('url') + "\n")
                                    break
        self.status.showMessage("All tasks complete", 5000)
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

# Entry-point
def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())