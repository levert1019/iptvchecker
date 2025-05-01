# main_window.py

import sys
import os
import queue
import re
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog
from playlist_sorter import sort_playlist

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
        self.group_entries = {}     # group_title -> [entry dicts]
        self.categories    = {}     # for OptionsDialog
        self.selected_groups = []

        # --- IPTV Options ---
        self.workers          = 5
        self.retries          = 2
        self.timeout          = 10
        self.split            = False
        self.update_quality   = False
        self.update_fps       = False
        self.include_untested = False
        self.output_dir       = os.getcwd()

        # --- Playlist Sorter flags ---
        self.enable_sorter = False
        self.tmdb_api_key  = ""

        # --- Runtime ---
        self.entry_map  = {}   # uid -> entry dict
        self.threads    = []   # WorkerThread[]
        self.log_records = []  # (level, msg)
        self._is_paused = False
        self._poll_timer = None

        # Build UI + load stylesheet
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

        # Load existing TMDB key from dontvconfig.txt
        self._load_config()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(0,0,0,0)
        main_v.setSpacing(0)

        # --- Script switcher bar ---
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #5b2fc9;")
        bl = QtWidgets.QHBoxLayout(bar)
        bl.setContentsMargins(10,0,0,0)

        self.btn_iptv = QtWidgets.QPushButton("IPTV Checker")
        self.btn_iptv.setCheckable(True)
        self.btn_iptv.setChecked(True)
        self.btn_iptv.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        self.btn_iptv.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        bl.addWidget(self.btn_iptv)

        self.btn_sorter = QtWidgets.QPushButton("Playlist Sorter")
        self.btn_sorter.setCheckable(True)
        self.btn_sorter.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        self.btn_sorter.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        bl.addWidget(self.btn_sorter)

        bl.addStretch()
        main_v.addWidget(bar)

        # --- Stacked pages ---
        self.pages = QtWidgets.QStackedWidget()
        main_v.addWidget(self.pages)

        # --- Page 0: IPTV Checker UI ---
        page0 = QtWidgets.QWidget()
        lv0 = QtWidgets.QVBoxLayout(page0)
        lv0.setContentsMargins(10,10,10,10)
        lv0.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:28pt;">Don</span>'
            '<span style="font-weight:bold; font-size:28pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:16pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        lv0.addWidget(hdr)

        # Controls Row
        ctrls = QtWidgets.QHBoxLayout()
        for text, slot in [
            ("Options", self._open_options),
            ("Start",   self.start_check),
            ("Pause",   self._toggle_pause),
            ("Stop",    self.stop_check),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(130,45)
            btn.clicked.connect(slot)
            if text == "Pause":
                self.btn_pause = btn
            ctrls.addWidget(btn)
            ctrls.addSpacing(10)
        ctrls.addStretch()
        lv0.addLayout(ctrls)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ('working','black_screen','non_working'):
            group = QtWidgets.QGroupBox(status.replace('_',' ').title())
            cols = 3 if status=='working' else 1
            hdrs = ['Channel','Res','FPS'] if status=='working' else ['Channel']
            tbl = QtWidgets.QTableWidget(0,cols)
            tbl.setHorizontalHeaderLabels(hdrs)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(group).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            panes.addWidget(group)
        lv0.addLayout(panes)

        # Console + filters
        console_box = QtWidgets.QGroupBox("Console")
        cv = QtWidgets.QVBoxLayout(console_box)
        fh = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_console)
            fh.addWidget(cb)
        cv.addLayout(fh)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        cv.addWidget(self.te_console)
        lv0.addWidget(console_box)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

        self.pages.addWidget(page0)

        # --- Page 1: Playlist Sorter UI ---
        page1 = QtWidgets.QWidget()
        lv1   = QtWidgets.QVBoxLayout(page1)
        lv1.setContentsMargins(10,10,10,10)
        lv1.setSpacing(10)

        # M3U selector
        m3u_h = QtWidgets.QHBoxLayout()
        m3u_h.addWidget(QtWidgets.QLabel("M3U File:"))
        self.le_sort_m3u = QtWidgets.QLineEdit()
        m3u_h.addWidget(self.le_sort_m3u,1)
        btn_b = QtWidgets.QPushButton("Browse…")
        btn_b.clicked.connect(self._browse_sort_m3u)
        m3u_h.addWidget(btn_b)
        lv1.addLayout(m3u_h)

        # API key
        api_h = QtWidgets.QHBoxLayout()
        api_h.addWidget(QtWidgets.QLabel("TMDB API Key:"))
        self.le_sort_api = QtWidgets.QLineEdit(self.tmdb_api_key)
        api_h.addWidget(self.le_sort_api,1)
        btn_s = QtWidgets.QPushButton("Save Key")
        btn_s.clicked.connect(self._save_sort_api)
        api_h.addWidget(btn_s)
        lv1.addLayout(api_h)

        # Workers + include untested
        opts_h = QtWidgets.QHBoxLayout()
        opts_h.addWidget(QtWidgets.QLabel("Workers:"))
        self.sp_sort_workers = QtWidgets.QSpinBox()
        self.sp_sort_workers.setRange(1,50)
        self.sp_sort_workers.setValue(self.workers)
        opts_h.addWidget(self.sp_sort_workers)
        self.cb_sort_include = QtWidgets.QCheckBox("Include untested")
        self.cb_sort_include.setChecked(self.include_untested)
        opts_h.addWidget(self.cb_sort_include)
        opts_h.addStretch()
        lv1.addLayout(opts_h)

        # Progress & groups & log
        self.pb_sort = QtWidgets.QProgressBar()
        lv1.addWidget(self.pb_sort)
        self.btn_sort_groups = QtWidgets.QPushButton("Select Groups…")
        self.btn_sort_groups.clicked.connect(self._open_sort_group_selector)
        lv1.addWidget(self.btn_sort_groups)
        self.btn_start_sort = QtWidgets.QPushButton("Start Sorter")
        self.btn_start_sort.clicked.connect(self.start_sorter)
        lv1.addWidget(self.btn_start_sort)
        self.te_sort_log = QtWidgets.QTextEdit()
        self.te_sort_log.setReadOnly(True)
        lv1.addWidget(self.te_sort_log,1)

        self.pages.addWidget(page1)

    def _load_config(self):
        cfg = os.path.join(os.getcwd(), "dontvconfig.txt")
        if os.path.isfile(cfg):
            with open(cfg,'r') as f:
                for ln in f:
                    if ln.startswith("TMDB_API_KEY="):
                        self.tmdb_api_key = ln.strip().split("=",1)[1]
                        self.enable_sorter = True
                        return

    def _open_options(self):
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        # --- Prefill existing values ---
        dlg.le_m3u.setText(self.m3u_file)
        dlg.sp_workers.setValue(self.workers)
        dlg.sp_retries.setValue(self.retries)
        dlg.sp_timeout.setValue(self.timeout)
        dlg.cb_split.setChecked(self.split)
        dlg.cb_update_quality.setChecked(self.update_quality)
        dlg.cb_update_fps.setChecked(self.update_fps)
        dlg.cb_include_untested.setChecked(self.include_untested)
        dlg.le_out.setText(self.output_dir)
        dlg.cb_sorter.setChecked(self.enable_sorter)
        dlg.le_api.setText(self.tmdb_api_key)
        if self.m3u_file:
            dlg.group_urls = self.group_entries
            dlg.categories = self.categories
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
            self.enable_sorter    = opts['enable_sorter']
            self.tmdb_api_key     = opts['tmdb_api_key']
            self.selected_groups  = opts['selected_groups']

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings",
                                          "Please select an M3U file and at least one group.")
            return

        # Read original M3U to preserve all lines
        with open(self.m3u_file,'r',encoding='utf-8') as f:
            self.original_lines = f.readlines()

        # Parse fresh
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        # Apply sorter if enabled
        if self.enable_sorter and self.tmdb_api_key:
            sorted_e, sorted_c = sort_playlist(
                self.group_entries, self.categories, self.tmdb_api_key
            )
            self.group_entries.update(sorted_e)
            self.categories.update(sorted_c)
            self.selected_groups += list(sorted_c.get('Sorted',[]))

        # Clear tables & console
        for s in ('working','black_screen','non_working'):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # Build entry_map & queue tasks
        self.entry_map = {e['uid']:e for grp in self.group_entries.values() for e in grp}
        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp,[]):
                q.put(e.copy())
        self.tasks_q = q
        self.status.showMessage(f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups",3000)

        # Launch workers
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # Poll completion with a QTimer
        if not self._poll_timer:
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._monitor_threads)
        self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        # Choose table
        tbl = {
            'UP':   self.tbl_working,
            'BLACK_SCREEN': self.tbl_black_screen
        }.get(status, self.tbl_non_working)

        row = tbl.rowCount()
        tbl.insertRow(row)

        # Build display name
        name = clean_name(entry['name'])
        if status == 'UP':
            if self.update_quality:
                q = resolution_to_label(res)
                if q: name += ' ' + q
            if self.update_fps:
                f = format_fps(fps)
                if f: name += ' ' + f

        # If sorter ran, override name & logo after UP
        if status == 'UP' and entry.get('_tmdb_title'):
            suffix = entry.get('_suffix','')
            newname = f"{entry['_tmdb_title']}{(' '+suffix) if suffix else ''}"
            entry['name'] = newname
            name = newname
            if entry.get('_tvg_logo'):
                entry['tvg-logo'] = entry['_tvg_logo']

        item = QtWidgets.QTableWidgetItem(name)
        item.setData(QtCore.Qt.UserRole, entry['uid'])
        tbl.setItem(row,0,item)

        if tbl is self.tbl_working:
            tbl.setItem(row,1,QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row,2,QtWidgets.QTableWidgetItem(str(fps)))

    def _on_log(self, level, msg):
        self.log_records.append((level,msg))
        self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show = {
            'working': self.cb_show_working.isChecked(),
            'info':    self.cb_show_info.isChecked(),
            'error':   self.cb_show_error.isChecked()
        }
        colors = {'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for lvl,m in self.log_records:
            if show.get(lvl,False):
                self.te_console.append(f"<span style='color:{colors[lvl]}'>{m}</span>")

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed",3000)

    def stop_check(self):
        for t in self.threads:
            t.stop()
        self.status.showMessage("Stopping...",2000)

    def _monitor_threads(self):
        if all(not t.isRunning() for t in self.threads):
            self._poll_timer.stop()
            self._write_output_files()

    def _write_output_files(self):
        # Rewrite original M3U, editing only the tested entries
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        outp = os.path.join(self.output_dir, f"{base}_updated.m3u")
        with open(outp,'w',encoding='utf-8') as fout:
            i = 0
            while i < len(self.original_lines):
                ln = self.original_lines[i]
                if ln.startswith("#EXTINF") and (m:=CUID_RE.search(ln)):
                    uid = m.group(1)
                    ent = self.entry_map.get(uid)
                    if ent:
                        attrs = [
                            f'CUID="{uid}"',
                            f'tvg-name="{ent["name"]}"',
                            f'tvg-logo="{ent.get("tvg-logo","")}"',
                            f'group-title="{ent.get("group-title","")}"'
                        ]
                        newext = "#EXTINF:0 "+" ".join(attrs)+","+ent["name"]+"\n"
                        fout.write(newext)
                        if i+1 < len(self.original_lines):
                            fout.write(self.original_lines[i+1])
                            i += 2
                            continue
                fout.write(ln)
                i += 1
        self.status.showMessage(f"Wrote updated M3U to {outp}",5000)

    # --- Playlist Sorter tab handlers (stubbed similarly) ---
    def _browse_sort_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select M3U", "", "M3U Files (*.m3u *.m3u8)")
        if path:
            self.le_sort_m3u.setText(path)

    def _save_sort_api(self):
        key = self.le_sort_api.text().strip()
        cfg = os.path.join(os.getcwd(),"dontvconfig.txt")
        lines = []
        if os.path.exists(cfg):
            lines = open(cfg).read().splitlines()
        with open(cfg,'w') as f:
            written=False
            for ln in lines:
                if ln.startswith("TMDB_API_KEY="):
                    f.write(f"TMDB_API_KEY={key}\n")
                    written=True
                else:
                    f.write(ln+"\n")
            if not written:
                f.write(f"TMDB_API_KEY={key}\n")
        QtWidgets.QMessageBox.information(self,"Saved","TMDB key saved.")
        self.tmdb_api_key = key

    def _open_sort_group_selector(self):
        # reuse the same GroupSelectionDialog
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        dlg.cb_sorter.setChecked(True)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups

    def start_sorter(self):
        # stub: implement your playlist_sorter.run_sorting here
        QtWidgets.QMessageBox.information(self,"Sorter","Sorting started (stub).")

    def closeEvent(self, event):
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()
        for t in self.threads:
            t.stop()
            t.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
