import sys
import os
import threading
import queue
import re
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog
from playlist_sorter import sort_playlist

# Regexes for rewriting EXTINF lines
extinf_tvg_re   = re.compile(r'(tvg-name=")[^"]*(")')
extinf_comma_re = re.compile(r'^(.*?,)(.*)$')

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

        # Data
        self.group_entries   = {}
        self.categories      = {}
        self.selected_groups = []
        self.m3u_file        = ""

        # Options defaults
        self.workers          = 5
        self.retries          = 2
        self.timeout          = 10
        self.split            = False
        self.update_quality   = False
        self.update_fps       = False
        self.include_untested = False
        self.output_dir       = os.getcwd()

        # Playlist sorter defaults
        self.tmdb_api_key  = ""
        cfg_path = os.path.join(os.getcwd(), "dontvconfig.txt")
        if os.path.isfile(cfg_path):
            with open(cfg_path, 'r') as cf:
                for line in cf:
                    if line.startswith('TMDB_API_KEY='):
                        self.tmdb_api_key = line.strip().split('=',1)[1]
                        break
        self.enable_sorter = bool(self.tmdb_api_key)

        # Runtime
        self.entry_map   = {}
        self.tasks_q     = None
        self.threads     = []
        self.log_records = []
        self._is_paused  = False

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(0,0,0,0)
        main_v.setSpacing(0)

        # Top bar
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color:#5b2fc9;")
        bl = QtWidgets.QHBoxLayout(bar)
        bl.setContentsMargins(10,0,0,0)
        btn_tab = QtWidgets.QPushButton("IPTV Checker")
        btn_tab.setCheckable(True)
        btn_tab.setChecked(True)
        btn_tab.setStyleSheet("color:white;background:transparent;border:none;font-weight:bold;")
        btn_tab.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        bl.addWidget(btn_tab)
        bl.addStretch()
        main_v.addWidget(bar)

        # Stacked pages
        self.pages = QtWidgets.QStackedWidget()
        main_v.addWidget(self.pages)

        # Page 0: main
        page = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(page)
        lv.setContentsMargins(10,10,10,10)
        lv.setSpacing(20)

        # Header
        hdr = QtWidgets.QLabel(
            '<span style="font-size:28pt;font-weight:bold;">Don</span>'
            '<span style="font-size:28pt;font-weight:bold;color:#5b2fc9;">TV</span>'
            '<span style="font-size:16pt;font-weight:bold;"> IPTV Checker</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        lv.addWidget(hdr)

        # Controls
        ctrl = QtWidgets.QHBoxLayout()
        for text, fn in [("Options",self._open_options), ("Start",self.start_check),
                         ("Pause",self._toggle_pause),("Stop",self.stop_check)]:
            b = QtWidgets.QPushButton(text)
            b.setFixedSize(130,45)
            b.clicked.connect(fn)
            if text=="Pause": self.btn_pause=b
            ctrl.addWidget(b); ctrl.addSpacing(10)
        ctrl.addStretch(); lv.addLayout(ctrl)

        # Result tables
        tables = QtWidgets.QHBoxLayout()
        for status in ('working','black_screen','non_working'):
            gb = QtWidgets.QGroupBox(status.replace('_',' ').title())
            cols = 3 if status=='working' else 1
            hdrs = ['Channel','Res','FPS'] if status=='working' else ['Channel']
            tbl = QtWidgets.QTableWidget(0,cols)
            tbl.setHorizontalHeaderLabels(hdrs)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            QtWidgets.QVBoxLayout(gb).addWidget(tbl)
            setattr(self, f"tbl_{status}", tbl)
            tables.addWidget(gb)
        lv.addLayout(tables)

        # Console
        cg = QtWidgets.QGroupBox("Console")
        cv = QtWidgets.QVBoxLayout(cg)
        fh = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working"); self.cb_show_working.setChecked(True)
        self.cb_show_info    = QtWidgets.QCheckBox("Show Info");    self.cb_show_info.setChecked(True)
        self.cb_show_error   = QtWidgets.QCheckBox("Show Error");   self.cb_show_error.setChecked(True)
        for cb in (self.cb_show_working,self.cb_show_info,self.cb_show_error):
            cb.stateChanged.connect(self._refresh_console); fh.addWidget(cb)
        cv.addLayout(fh)
        self.te_console = QtWidgets.QTextEdit(); self.te_console.setReadOnly(True)
        cv.addWidget(self.te_console); lv.addWidget(cg)

        # Status bar
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.pages.addWidget(page)

    def _open_options(self):
        dlg = OptionsDialog(self.categories, self.group_entries, self)
        # preload current
        dlg.le_m3u.setText(self.m3u_file)
        dlg.sp_workers.setValue(self.workers);
        dlg.sp_retries.setValue(self.retries);
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
            dlg.group_urls = self.group_entries; dlg.categories = self.categories
            dlg.selected_groups = list(self.selected_groups)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.m3u_file        = dlg.le_m3u.text()
            self.selected_groups = dlg.selected_groups
            self.workers         = dlg.sp_workers.value()
            self.retries         = dlg.sp_retries.value()
            self.timeout         = dlg.sp_timeout.value()
            self.split           = dlg.cb_split.isChecked()
            self.update_quality  = dlg.cb_update_quality.isChecked()
            self.update_fps      = dlg.cb_update_fps.isChecked()
            self.include_untested= dlg.cb_include_untested.isChecked()
            self.output_dir      = dlg.le_out.text()
            self.enable_sorter   = dlg.cb_sorter.isChecked()
            self.tmdb_api_key    = dlg.le_api.text().strip()
            self.group_entries, self.categories = parse_groups(self.m3u_file)

    def start_check(self):
        if not (self.m3u_file and self.selected_groups):
            QtWidgets.QMessageBox.warning(self,"Missing Settings","Select M3U and groups.")
            return
        # refresh API key from config
        cfg = os.path.join(os.getcwd(),"dontvconfig.txt")
        if os.path.isfile(cfg):
            with open(cfg,'r') as cf:
                for ln in cf:
                    if ln.startswith('TMDB_API_KEY='):
                        self.tmdb_api_key = ln.split('=',1)[1].strip()
                        break
        if self.enable_sorter and self.tmdb_api_key:
            # separate live vs movies/series
            live_sel = [g for g in self.selected_groups if g in self.categories.get('Live',[])]
            sorted_entries, sorted_cats = sort_playlist(self.group_entries, self.categories, self.tmdb_api_key)
            # merge: keep live original, use sorted for movies/series
            self.group_entries = {g: self.group_entries[g] for g in live_sel}
            self.group_entries.update(sorted_entries)
            self.selected_groups = live_sel + list(sorted_entries.keys())
        # clear
        for s in ('working','black_screen','non_working'):
            getattr(self,f"tbl_{s}").setRowCount(0)
        self.log_records.clear(); self.te_console.clear()
        # queue tasks
        self.entry_map = {e['uid']:e for grp in self.group_entries.values() for e in grp}
        self.tasks_q   = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp,[]):
                self.tasks_q.put(e.copy())
        self._on_log('info',f"Queued {self.tasks_q.qsize()} tasks from {len(self.selected_groups)} groups")
        # start workers
        self.threads=[]
        for _ in range(self.workers):
            t=WorkerThread(self.tasks_q,self.retries,self.timeout)
            t.result.connect(self._on_result); t.log.connect(self._on_log); t.start(); self.threads.append(t)
        # poll threads
        if hasattr(self,'_poll_timer'): self._poll_timer.stop()
        self._poll_timer=QtCore.QTimer(self); self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._monitor_threads); self._poll_timer.start()
        self.status.showMessage("Checking started",3000)

    def _on_result(self,entry,status,res,fps):
        tbl = {'UP':self.tbl_working,'BLACK_SCREEN':self.tbl_black_screen}.get(status,self.tbl_non_working)
        r=tbl.rowCount(); tbl.insertRow(r)
        d=clean_name(entry['name'])
        if status=='UP':
            if self.update_quality:
                q=resolution_to_label(res); d+=f' {q}' if q else ''
            if self.update_fps:
                f=format_fps(fps); d+=f' {f}' if f else ''
        it=QtWidgets.QTableWidgetItem(d); it.setData(QtCore.Qt.UserRole,entry['uid']); tbl.setItem(r,0,it)
        if tbl is self.tbl_working:
            tbl.setItem(r,1,QtWidgets.QTableWidgetItem(res)); tbl.setItem(r,2,QtWidgets.QTableWidgetItem(fps))

    def _on_log(self,level,msg):
        self.log_records.append((level,msg)); self._refresh_console()
    def _refresh_console(self):
        self.te_console.clear(); show={'working':self.cb_show_working.isChecked(),'info':self.cb_show_info.isChecked(),'error':self.cb_show_error.isChecked()}; col={'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for l,m in self.log_records:
            if show.get(l): self.te_console.append(f"<span style='color:{col[l]}'>{m}</span>")
    def _toggle_pause(self):
        self._is_paused=not self._is_paused; [t.pause() if self._is_paused else t.resume() for t in self.threads]
        self.btn_pause.setText("Resume" if self._is_paused else "Pause"); self.status.showMessage("Paused" if self._is_paused else "Resumed",3000)
    def stop_check(self):
        [t.stop() for t in self.threads]; self.status.showMessage("Stopping...",2000)
    def _monitor_threads(self):
        if all(not t.isRunning() for t in self.threads): self._poll_timer.stop(); self._start_writing()
    def _start_writing(self):
        threading.Thread(target=self._write_output_files,daemon=True).start()
    def _write_output_files(self):
        if not self.m3u_file: return
        base=os.path.splitext(os.path.basename(self.m3u_file))[0]; outd=self.output_dir
        if self.split:
            for k,suf in [('working','_working'),('black_screen','_blackscreen'),('non_working','_notworking')]:
                fn=os.path.join(outd,f"{base}{suf}.m3u");
                with open(fn,'w',encoding='utf-8') as f:
                    for i in range(getattr(self,f"tbl_{k}").rowCount()):
                        uid=getattr(self,f"tbl_{k}").item(i,0).data(QtCore.Qt.UserRole); f.write(self.entry_map[uid]['url']+"\n")
                self.status.showMessage(f"Wrote {fn}",3000)
        else:
            fn=os.path.join(outd,f"{base}_all.m3u");
            with open(fn,'w',encoding='utf-8') as f:
                for tblname in ['working','black_screen','non_working']:
                    tbl=getattr(self,f"tbl_{tblname}")
                    for i in range(tbl.rowCount()): uid=tbl.item(i,0).data(QtCore.Qt.UserRole); f.write(self.entry_map[uid]['url']+"\n")
            self.status.showMessage(f"Wrote {fn}",3000)
        self.status.showMessage("All tasks complete",5000)

if __name__ == '__main__':
    run_gui()
