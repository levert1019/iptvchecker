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

# Regexes (if you need them elsewhere)
extinf_attr_keys = [
    'CUID', 'tvg-name', 'tvg-id',
    'catchup-type', 'catchup-days',
    'tvg-logo', 'group-title'
]


class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)

        # Configuration & state
        self.m3u_file = ""
        self.group_entries = {}    # group_title -> list of entry dicts
        self.categories = {}       # same keys for OptionsDialog
        self.selected_groups = []

        # Options
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False
        self.output_dir = os.getcwd()

        # Playlist sorter
        self.enable_sorter = False
        self.tmdb_api_key = ""

        # Runtime
        self.entry_map = {}       # uid -> entry dict
        self.threads = []         # WorkerThread instances
        self.log_records = []     # (level, msg) tuples
        self._is_paused = False
        self._poll_timer = None

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

        # Load config (TMDB key) on start
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
        bar_layout = QtWidgets.QHBoxLayout(bar)
        bar_layout.setContentsMargins(10,0,0,0)
        btn_iptv = QtWidgets.QPushButton("IPTV Checker")
        btn_iptv.setCheckable(True)
        btn_iptv.setChecked(True)
        btn_iptv.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        btn_iptv.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        bar_layout.addWidget(btn_iptv)
        bar_layout.addStretch()
        main_v.addWidget(bar)

        # --- Pages container ---
        self.pages = QtWidgets.QStackedWidget()
        main_v.addWidget(self.pages)

        # --- Page 0: IPTV Checker ---
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-weight:bold; font-size:28pt;">Don</span>'
            '<span style="font-weight:bold; font-size:28pt; color:#5b2fc9;">TV</span>'
            '<span style="font-weight:bold; font-size:16pt;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hdr)

        # Top buttons
        top_h = QtWidgets.QHBoxLayout()
        for text, slot in [
            ("Options", self._open_options),
            ("Start", self.start_check),
            ("Pause", self._toggle_pause),
            ("Stop", self.stop_check),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(130, 45)
            btn.clicked.connect(slot)
            if text == "Pause":
                self.btn_pause = btn
            top_h.addWidget(btn)
            top_h.addSpacing(10)
        top_h.addStretch()
        layout.addLayout(top_h)

        # Result tables
        panes = QtWidgets.QHBoxLayout()
        for status in ('working','black_screen','non_working'):
            grp = QtWidgets.QGroupBox(status.replace('_',' ').title())
            cols = 3 if status=='working' else 1
            hdrs = ['Channel','Res','FPS'] if status=='working' else ['Channel']
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(hdrs)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(grp).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            panes.addWidget(grp)
        layout.addLayout(panes)

        # Console + filters
        console_grp = QtWidgets.QGroupBox("Console")
        console_v = QtWidgets.QVBoxLayout(console_grp)
        filt_h = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_console)
            filt_h.addWidget(cb)
        console_v.addLayout(filt_h)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_v.addWidget(self.te_console)
        layout.addWidget(console_grp)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

        self.pages.addWidget(page)

    def _load_config(self):
        cfg = os.path.join(os.getcwd(), "dontvconfig.txt")
        if os.path.isfile(cfg):
            with open(cfg, 'r') as f:
                for line in f:
                    if line.startswith("TMDB_API_KEY="):
                        self.tmdb_api_key = line.strip().split("=",1)[1]
                        self.enable_sorter = True
                        break

    def _open_options(self):
        dlg = OptionsDialog(self.categories, self.group_entries, parent=self)
        # Prefill
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
            self.group_entries, self.categories = parse_groups(self.m3u_file)

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
            # Re-parse groups
            self.group_entries, self.categories = parse_groups(self.m3u_file)

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings",
                                          "Please select an M3U file and at least one group.")
            return

        # reload config key
        self._load_config()

        # parse groups fresh
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        # apply sorter if enabled
        if self.enable_sorter and self.tmdb_api_key:
            sorted_entries, sorted_cats = sort_playlist(
                self.group_entries, self.categories, self.tmdb_api_key
            )
            # merge sorted results
            self.group_entries.update(sorted_entries)
            self.categories.update(sorted_cats)
            # include sorted groups
            self.selected_groups += list(sorted_cats.get('Sorted', []))

        # clear UI
        for s in ('working','black_screen','non_working'):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()

        # build entry_map and queue
        self.entry_map = {e['uid']: e for grp in self.group_entries.values() for e in grp}
        q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                q.put(e.copy())
        self.tasks_q = q
        self.status.showMessage(f"Queued {q.qsize()} tasks from {len(self.selected_groups)} groups", 3000)

        # spawn workers
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)

        # set up polling timer
        if not self._poll_timer:
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._monitor_threads)
        self._poll_timer.start()

    def _on_result(self, entry, status, res, fps):
        # pick table
        tbl = {
            'UP': self.tbl_working,
            'BLACK_SCREEN': self.tbl_black_screen
        }.get(status, self.tbl_non_working)

        row = tbl.rowCount()
        tbl.insertRow(row)

        # basic display
        display = clean_name(entry['name'])
        if status == 'UP':
            if self.update_quality:
                qlab = resolution_to_label(res)
                if qlab:
                    display += ' ' + qlab
            if self.update_fps:
                flab = format_fps(fps)
                if flab:
                    display += ' ' + flab

        # apply TMDB rename/logo after UP
        if status == 'UP' and entry.get('_tmdb_title'):
            suffix = entry.get('_suffix','')
            display = entry['_tmdb_title'] + (f" {suffix}" if suffix else "")
            # override logo attribute
            if entry.get('_tvg_logo'):
                entry['tvg-logo'] = entry['_tvg_logo']
            entry['name'] = display

        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, entry['uid'])
        tbl.setItem(row, 0, item)

        if tbl is self.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(fps)))

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
        colors = {'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for lvl, m in self.log_records:
            if show.get(lvl, False):
                self.te_console.append(f"<span style='color:{colors[lvl]}'>{m}</span>")

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads:
            t.pause() if self._is_paused else t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed", 3000)

    def stop_check(self):
        # signal all workers to stop
        for t in self.threads:
            t.stop()
        self.status.showMessage("Stopping...", 2000)

    def _monitor_threads(self):
        if all(not t.isRunning() for t in self.threads):
            self._poll_timer.stop()
            self._write_output_files()

    def _write_output_files(self):
        if not self.m3u_file:
            return
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        outd = self.output_dir or os.getcwd()

        # write single or split
        if self.split:
            for key, suffix in [
                ('working','_working'),
                ('black_screen','_blackscreen'),
                ('non_working','_notworking')
            ]:
                fn = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(fn, 'w', encoding='utf-8') as f:
                    for grp in self.selected_groups:
                        for entry in self.group_entries.get(grp, []):
                            attrs = []
                            for k in extinf_attr_keys:
                                if k in entry:
                                    attrs.append(f'{k}="{entry[k]}"')
                            f.write(f"#EXTINF:0 {' '.join(attrs)},{entry['name']}\n")
                            f.write(entry['url'] + "\n")
                self.status.showMessage(f"Wrote {fn}", 3000)
        else:
            fn = os.path.join(outd, f"{base}_all.m3u")
            with open(fn, 'w', encoding='utf-8') as f:
                for grp in self.selected_groups:
                    for entry in self.group_entries.get(grp, []):
                        attrs = []
                        for k in extinf_attr_keys:
                            if k in entry:
                                attrs.append(f'{k}="{entry[k]}"')
                        f.write(f"#EXTINF:0 {' '.join(attrs)},{entry['name']}\n")
                        f.write(entry['url'] + "\n")
            self.status.showMessage(f"Wrote {fn}", 3000)

    def closeEvent(self, event):
        # clean up timer
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()
        # stop and wait on threads
        for t in self.threads:
            t.stop()
            t.wait()
        super().closeEvent(event)


# If run directly, launch the application
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
