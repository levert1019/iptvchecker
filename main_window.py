import sys
import os
import threading
import queue

from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from utils import clean_name, resolution_to_label, format_fps
from styles import STYLE_SHEET
from options import OptionsDialog


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

        # Data loaded from M3U
        self.group_entries = {}   # group name -> list of entries (dicts with extinf,name,url)
        self.categories = {}      # category info

        # User options state
        self.m3u_file = ""
        self.selected_groups = []
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False
        self.output_dir = os.getcwd()

        # Runtime
        self.entry_map = {}      # name -> entry dict for all channels
        self.tasks_q = None
        self.threads = []
        self.log_records = []    # list of (level, message)
        self._is_paused = False
        self.written = []

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
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

        # Buttons row
        btn_layout = QtWidgets.QHBoxLayout()
        for text, slot in [
            ("Options", self._open_options),
            ("Start", self.start_check),
            ("Pause", self._toggle_pause),
            ("Stop", self.stop_check)
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedSize(100, 40)
            btn.clicked.connect(slot)
            if text == "Pause":
                self.btn_pause = btn
            btn_layout.addWidget(btn)
            btn_layout.addSpacing(10)
        layout.addLayout(btn_layout)

        # Result tables
        tables_layout = QtWidgets.QHBoxLayout()
        for status in ("working", "black_screen", "non_working"):
            grp = QtWidgets.QGroupBox(status.replace("_"," ").title())
            if status == "working":
                cols, headers = 3, ["Channel","Res","FPS"]
            else:
                cols, headers = 1, ["Channel"]
            tbl = QtWidgets.QTableWidget(0, cols)
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            vbox = QtWidgets.QVBoxLayout(grp)
            vbox.addWidget(tbl)
            tables_layout.addWidget(grp)
            setattr(self, f"tbl_{status}", tbl)
        layout.addLayout(tables_layout)

        # Console + filters
        console_grp = QtWidgets.QGroupBox("Console")
        console_layout = QtWidgets.QVBoxLayout(console_grp)
        filter_layout = QtWidgets.QHBoxLayout()
        self.cb_show_working = QtWidgets.QCheckBox("Show Working")
        self.cb_show_info = QtWidgets.QCheckBox("Show Info")
        self.cb_show_error = QtWidgets.QCheckBox("Show Error")
        for cb in (self.cb_show_working, self.cb_show_info, self.cb_show_error):
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_console)
            filter_layout.addWidget(cb)
        console_layout.addLayout(filter_layout)
        self.te_console = QtWidgets.QTextEdit()
        self.te_console.setReadOnly(True)
        console_layout.addWidget(self.te_console)
        layout.addWidget(console_grp)

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
            # load options
            self.m3u_file = dlg.le_m3u.text()
            self.selected_groups = dlg.selected_groups
            self.workers = dlg.sp_workers.value()
            self.retries = dlg.sp_retries.value()
            self.timeout = dlg.sp_timeout.value()
            self.split = dlg.cb_split.isChecked()
            self.update_quality = dlg.cb_update_quality.isChecked()
            self.update_fps = dlg.cb_update_fps.isChecked()
            self.include_untested = dlg.cb_include_untested.isChecked()
            self.output_dir = dlg.le_out.text()
            # parse file
            self.group_entries, self.categories = parse_groups(self.m3u_file)

    def start_check(self):
        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "Missing Settings", "Select an M3U and groups.")
            return
        # clear
        for s in ("working","black_screen","non_working"):
            getattr(self, f"tbl_{s}").setRowCount(0)
        self.log_records.clear()
        self.te_console.clear()
        self.written.clear()
        # build entry_map from all entries
        self.entry_map = {e['name']:e for ent in self.group_entries.values() for e in ent}
        # queue tasks
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for e in self.group_entries.get(grp, []):
                self.tasks_q.put((e['name'], e['url']))
        # start
        self._on_log('info', f"Selected {len(self.selected_groups)} groups")
        self.threads = []
        for _ in range(self.workers):
            t = WorkerThread(self.tasks_q, self.retries, self.timeout)
            t.result.connect(self._on_result)
            t.log.connect(self._on_log)
            t.start()
            self.threads.append(t)
        threading.Thread(target=self._monitor_threads, daemon=True).start()
        self.status.showMessage("Checking started",3000)

    def _on_result(self, name, status, res, fps):
        if status=='UP': key='working'
        elif status=='BLACK_SCREEN': key='black_screen'
        else: key='non_working'
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount(); tbl.insertRow(row)
        display = clean_name(name)
        if status=='UP':
            if self.update_quality:
                q = resolution_to_label(res)
                if q: display += ' '+q
            if self.update_fps:
                f = format_fps(fps)
                if f: display += ' '+f
        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole,name)
        tbl.setItem(row,0,item)
        if key=='working':
            tbl.setItem(row,1,QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row,2,QtWidgets.QTableWidgetItem(fps))

    def _on_log(self, level, msg):
        self.log_records.append((level,msg)); self._refresh_console()

    def _refresh_console(self):
        self.te_console.clear()
        show={'working':self.cb_show_working.isChecked(),
              'info':self.cb_show_info.isChecked(),
              'error':self.cb_show_error.isChecked()}
        cols={'working':'#00ff00','info':'#ffa500','error':'#ff0000'}
        for lvl,m in self.log_records:
            if show.get(lvl): self.te_console.append(f'<span style="color:{cols[lvl]}">{m}</span>')

    def _toggle_pause(self):
        self._is_paused=not self._is_paused
        for t in self.threads:
            (t.pause() if self._is_paused else t.resume())
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        self.status.showMessage("Paused" if self._is_paused else "Resumed",2000)

    def stop_check(self):
        for t in self.threads: t.stop()

    def _monitor_threads(self):
        for t in self.threads: t.wait()
        QtCore.QTimer.singleShot(0,self._start_writing)

    def _start_writing(self): threading.Thread(target=self._write_output_files,daemon=True).start()

    def _write_output_files(self):
        if not self.m3u_file: return
        base=os.path.splitext(os.path.basename(self.m3u_file))[0]
        paths=[]
        tested,disp_map=set(),{}
        for st in('working','black_screen','non_working'):
            tbl=getattr(self,f"tbl_{st}")
            for r in range(tbl.rowCount()):
                it=tbl.item(r,0);orig=it.data(QtCore.Qt.UserRole)
                tested.add(orig); disp_map[orig]=it.text()
        def write(fn,names):
            with open(fn,'w',encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for orig in names:
                    ent=self.entry_map.get(orig)
                    if not ent: continue
                    if orig in tested:
                        pref=ent['extinf'].split(',',1)[0];f.write(f"{pref},{disp_map[orig]}\n")
                    else: f.write(ent['extinf']+'\n')
                    f.write(ent['url']+'\n')
            paths.append(fn)
        # working
        w=[self.tbl_working.item(r,0).data(QtCore.Qt.UserRole) for r in range(self.tbl_working.rowCount())]
        write(os.path.join(self.output_dir,f"{base}_working.m3u"),w)
        if self.split:
            b=[self.tbl_black_screen.item(r,0).data(QtCore.Qt.UserRole) for r in range(self.tbl_black_screen.rowCount())]
            write(os.path.join(self.output_dir,f"{base}_blackscreen.m3u"),b)
            n=[self.tbl_non_working.item(r,0).data(QtCore.Qt.UserRole) for r in range(self.tbl_non_working.rowCount())]
            write(os.path.join(self.output_dir,f"{base}_notworking.m3u"),n)
        if self.include_untested:
            alln=list(self.entry_map.keys()); write(os.path.join(self.output_dir,f"{base}_all.m3u"),alln)
        self.written=paths; QtCore.QTimer.singleShot(0,self._on_files_written)

    def _on_files_written(self):
        for p in self.written: self._on_log('info',f"Wrote output file: {p}")
        self._on_log('info','All tasks complete'); self.status.showMessage('All tasks complete',3000)


if __name__=="__main__": run_gui()
