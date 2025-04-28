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

def sup_digits(text: str) -> str:
    """Convert digits to superscript."""
    tbl = str.maketrans({
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
    })
    return text.translate(tbl)

def format_fps(text: str) -> str:
    """Extract numeric fps, drop '/1' or trailing .0, convert to superscript + 'ᶠᵖˢ'."""
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not m:
        return '–'
    num = m.group(1)
    if num.endswith('.0'):
        num = num[:-2]
    return f"{sup_digits(num)}ᶠᵖˢ"

def resolution_to_label(res: str) -> str:
    """Map a resolution string 'WIDTH×HEIGHT' to a quality label."""
    parts = res.split('×')
    if len(parts) != 2:
        return ''
    try:
        w, h = map(int, parts)
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

def clean_name(name: str) -> str:
    """Remove existing quality/fps tokens from the channel name."""
    name = re.sub(r"\d+ᶠᵖˢ", '', name)
    for v in QUALITY_LABELS.values():
        name = name.replace(v, '')
    name = re.sub(r"\b(sd|hd|fhd|uhd)\b", '', name, flags=re.IGNORECASE)
    name = re.sub(r"\b\d+(?:\.\d+)?fps\b", '', name, flags=re.IGNORECASE)
    return name.strip()

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # Parsed data
        self.group_urls      = {}
        self.categories      = {}
        self.selected_groups = []

        # Runtime state
        self.tasks_q     = None
        self.threads     = []
        self.results     = {}   # name -> (res, fps)
        self.url_map     = {}   # name -> url
        self.extinf_map  = {}   # name -> raw EXTINF line
        self.status_map  = {}   # name -> table key
        self.log_records = []   # list of (level, message)
        self.remaining   = 0
        self._is_paused  = False

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(10,10,10,10)
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
        self.le_m3u     = QtWidgets.QLineEdit();      h0.addWidget(self.le_m3u)
        btn_browse      = QtWidgets.QPushButton("Browse M3U"); btn_browse.clicked.connect(self._on_browse_m3u); h0.addWidget(btn_browse)
        self.btn_select = QtWidgets.QPushButton("Select Groups"); self.btn_select.setEnabled(False); self.btn_select.clicked.connect(self._on_select_groups); h0.addWidget(self.btn_select)
        v.addLayout(h0)

        # Options
        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(QtWidgets.QLabel("Workers:"))
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,50); self.sp_workers.setValue(5); h1.addWidget(self.sp_workers)
        h1.addWidget(QtWidgets.QLabel("Retries:"))
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(1,10); self.sp_retries.setValue(2); h1.addWidget(self.sp_retries)
        h1.addWidget(QtWidgets.QLabel("Timeout (s):"))
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10); h1.addWidget(self.sp_timeout)
        self.cb_split       = QtWidgets.QCheckBox("Split into Files");       h1.addWidget(self.cb_split)
        self.cb_update_name = QtWidgets.QCheckBox("Update Quality in Name"); h1.addWidget(self.cb_update_name)
        h1.addWidget(QtWidgets.QLabel("Out Folder:"))
        self.le_out = QtWidgets.QLineEdit(); self.le_out.setPlaceholderText("Select output folder…"); h1.addWidget(self.le_out)
        btn_out = QtWidgets.QPushButton("Browse"); btn_out.clicked.connect(self._on_browse_out); h1.addWidget(btn_out)
        v.addLayout(h1)

        # Control buttons
        h2 = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start"); h2.addWidget(self.btn_start)
        self.btn_pause = QtWidgets.QPushButton("Pause"); self.btn_pause.setEnabled(False); h2.addWidget(self.btn_pause)
        self.btn_stop  = QtWidgets.QPushButton("Stop");  self.btn_stop.setEnabled(False);  h2.addWidget(self.btn_stop)
        v.addLayout(h2)
        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_stop.clicked.connect(self.stop_check)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for title in ["Working","Black Screen","Non Working"]:
            box = QtWidgets.QGroupBox(title)
            tbl = QtWidgets.QTableWidget(0,3)
            tbl.setHorizontalHeaderLabels(["Channel","Res","FPS"])
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            tbl.setStyleSheet(
                "QHeaderView::section { background-color: #2b2b2b; color: #e0e0e0; }"
                "QTableWidget { background-color: #3c3f41; color: #e0e0e0; }"
                "QTableWidget::item:selected { background-color: #5b2fc9; color: white; }"
            )
            QtWidgets.QVBoxLayout(box).addWidget(tbl)
            panes.addWidget(box)
            setattr(self, f"tbl_{title.lower().replace(' ','_')}", tbl)
        v.addLayout(panes)

        # Console + filters
        grpC = QtWidgets.QGroupBox("Console")
        vg   = QtWidgets.QVBoxLayout(grpC)
        hf2  = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True); hf2.addWidget(self.cb_show_working)
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info");    self.cb_show_info.setChecked(True);    hf2.addWidget(self.cb_show_info)
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error");   self.cb_show_error.setChecked(True);   hf2.addWidget(self.cb_show_error)
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.stateChanged.connect(self._refresh_console)
        vg.addLayout(hf2)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True); vg.addWidget(self.te_console)
        v.addWidget(grpC)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.setCentralWidget(central)

    def _on_browse_m3u(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select M3U File", "", "M3U Files (*.m3u)")
        if fn:
            self.le_m3u.setText(fn)
            # parse_groups returns a dict of lists with entries: {group: [{'name','url','extinf'},...], ...}
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

        # Reset all state
        self.results.clear()
        self.url_map.clear()
        self.extinf_map.clear()
        self.status_map.clear()
        self.log_records.clear()
        for tbl in (self.tbl_working, self.tbl_black_screen, self.tbl_non_working):
            tbl.setRowCount(0)

        # Queue tasks and build maps
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for ent in self.group_urls.get(grp, []):
                name, url, ext = ent['name'], ent['url'], ent['extinf']
                self.tasks_q.put((name, url))
                self.url_map[name]   = url
                self.extinf_map[name] = ext

        # Spawn worker threads
        self.threads   = []
        self.remaining = self.sp_workers.value()
        for _ in range(self.remaining):
            t = WorkerThread(self.tasks_q, self.sp_retries.value(), self.sp_timeout.value())
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.finished.connect(self._thread_done)
            t.start()
            self.threads.append(t)

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.status.showMessage("Checking started", 3000)

    def _thread_done(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self._finish_up()

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
        threading.Thread(target=self._finish_up, daemon=True).start()

    def _on_result(self, name, status, res, fps):
        self.results[name] = (res, fps)
        key = 'working' if status == 'UP' else 'black_screen' if status == 'BLACK_SCREEN' else 'non_working'
        self.status_map[name] = key
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount(); tbl.insertRow(row)

        # Format display name
        formatted = name
        formatted = re.sub(r"\b(sd|hd|fhd|uhd)\b",
                           lambda m: QUALITY_LABELS[m.group(1).lower()],
                           formatted, flags=re.IGNORECASE)
        formatted = re.sub(r"\d+(?:/\d+)?bps?",
                           lambda m: format_fps(m.group(0)),
                           formatted, flags=re.IGNORECASE)
        if self.cb_update_name.isChecked():
            base = clean_name(formatted)
            qual = resolution_to_label(res)
            fsup = format_fps(fps)
            formatted = f"{base} {qual} {fsup}".strip()

        m = re.search(r"(\d+(?:\.\d+)?)", fps or "")
        num = m.group(1) if m else ''
        if num.endswith('.0'):
            num = num[:-2]

        tbl.setItem(row, 0, QtWidgets.QTableWidgetItem(formatted))
        tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
        tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(num or '–'))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        show = {
            'working': self.cb_show_working.isChecked(),
            'info':    self.cb_show_info.isChecked(),
            'error':   self.cb_show_error.isChecked(),
        }
        cmap = {'working':'#00ff00', 'info':'#ffa500', 'error':'#ff0000'}
        self.te_console.clear()
        for lvl, raw in self.log_records:
            if not show.get(lvl):
                continue
            parts = raw.split('[', 1)
            prefix = parts[0].strip()
            prefix = re.sub(r"\b(sd|hd|fhd|uhd)\b",
                            lambda m: QUALITY_LABELS[m.group(1).lower()],
                            prefix, flags=re.IGNORECASE)
            prefix = re.sub(r"\d+(?:/\d+)?bps?",
                            lambda m: format_fps(m.group(0)),
                            prefix, flags=re.IGNORECASE)
            disp = prefix
            if len(parts) > 1:
                inner = parts[1].rstrip(']')
                rstr, fpsp = inner.split(',', 1)
                if self.cb_update_name.isChecked():
                    cn  = clean_name(prefix)
                    lbl = resolution_to_label(rstr.strip())
                    fs  = format_fps(fpsp)
                    disp = f"{cn} {lbl} {fs}".strip()
                else:
                    fs = format_fps(fpsp)
                    disp = f"{prefix} [{rstr.strip()}, {fs}]"
            self.te_console.append(f'<span style="color:{cmap[lvl]}">{disp}</span>')

    def _finish_up(self):
        outd = self.le_out.text() or os.getcwd()
        os.makedirs(outd, exist_ok=True)
        base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]

        # Write combined playlist
        combined = os.path.join(outd, f"{base}.m3u")
        with open(combined, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for name in self.results:
                ext = self.extinf_map.get(name, '')
                if self.cb_update_name.isChecked() and ext:
                    # Update tvg-name attribute
                    new_nm = f"{clean_name(name)} {resolution_to_label(self.results[name][0])} {format_fps(self.results[name][1])}".strip()
                    ext = re.sub(r'tvg-name="[^"]*"', f'tvg-name="{new_nm}"', ext)
                    # Update trailing channel label
                    ext = re.sub(r",.*$", f",{new_nm}", ext)
                f.write(ext + "\n")
                url = self.url_map.get(name, '')
                if url:
                    f.write(url + "\n")

        # Write split playlists if requested
        if self.cb_split.isChecked():
            for key, suffix in [('working','_working'),('black_screen','_blackscreen'),('non_working','_nonworking')]:
                path = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for name, status in self.status_map.items():
                        if status == key:
                            ext = self.extinf_map.get(name, '')
                            if self.cb_update_name.isChecked() and ext:
                                new_nm = f"{clean_name(name)} {resolution_to_label(self.results[name][0])} {format_fps(self.results[name][1])}".strip()
                                ext = re.sub(r'tvg-name="[^"]*"', f'tvg-name="{new_nm}"', ext)
                                ext = re.sub(r",.*$", f",{new_nm}", ext)
                            f.write(ext + "\n")
                            url = self.url_map.get(name, '')
                            if url:
                                f.write(url + "\n")

        # Reset UI
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.status.showMessage("All tasks complete", 5000)

# Entry-point
def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
