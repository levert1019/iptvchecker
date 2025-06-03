import os
import threading
import traceback
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QTextCursor
from services.parser import parse_groups
from services.output_writer import write_output_files, CUID_RE
from services.utils import clean_name, resolution_to_label, format_fps
import requests

class CheckRunnable(QtCore.QObject, QtCore.QRunnable):
    """QRunnable that emits a result when done."""
    result = QtCore.pyqtSignal(dict, str, str, str)  # entry, status, resolution, fps
    log    = QtCore.pyqtSignal(str, str)             # level, message

    def __init__(self, entry, retries, timeout):
        super().__init__()
        QtCore.QRunnable.__init__(self)
        self.entry   = entry
        self.retries = retries
        self.timeout = timeout
        self.setAutoDelete(True)

    def run(self):
        url     = self.entry['url']
        attempt = 0
        status  = 'DOWN'
        while attempt <= self.retries:
            try:
                r = requests.get(url, timeout=self.timeout, stream=True)
                if r.status_code == 200:
                    status = 'UP'
                    break
            except Exception as e:
                self.log.emit('error', f"Error on {self.entry['uid']}: {e}")
            attempt += 1
        # no resolution/fps detection
        self.result.emit(self.entry, status, '', '')


class CheckerController(QtCore.QObject):
    log_signal    = QtCore.pyqtSignal(str, str)             # (level, message)
    status_signal = QtCore.pyqtSignal(str, int)             # (message, timeout_ms)
    result_signal = QtCore.pyqtSignal(dict, str, str, str)  # (entry, status, resolution, fps)

    def __init__(self, ui, options_dialog, main_window):
        super().__init__(main_window)
        self.ui        = ui
        self.opts      = options_dialog
        self.main      = main_window
        self.pool      = QtCore.QThreadPool.globalInstance()
        self.remaining = 0

        # connect signals
        self.log_signal.connect(self._on_log)
        self.status_signal.connect(self.main.statusBar().showMessage)
        self.result_signal.connect(self._on_result)
        self._connect_signals()

    def _connect_signals(self):
        self.ui.btn_start.clicked.connect(self._start_safe)
        self.ui.btn_pause.clicked.connect(self._toggle_pause)
        self.ui.btn_stop.clicked.connect(self.stop_check)
        for lvl in ('working', 'info', 'error'):
            cb = getattr(self.ui, f'cb_show_{lvl}', None)
            if cb:
                cb.stateChanged.connect(self._refresh_console)

    def _start_safe(self):
        try:
            self.start_check()
        except Exception:
            err = traceback.format_exc()
            self.log_signal.emit('error', 'Exception in start_check')
            QtWidgets.QMessageBox.critical(
                self.ui,
                'Critical Error',
                f'An exception occurred:\n{err}'
            )
            traceback.print_exc()

    def start_check(self):
        opts = self.opts.get_options()
        self.m3u_file         = opts.get('m3u_file', '')
        self.workers          = opts.get('workers', 5)
        self.retries          = opts.get('retries', 2)
        self.timeout          = opts.get('timeout', 10)
        self.split            = opts.get('split', False)
        self.update_quality   = opts.get('update_quality', False)
        self.update_fps       = opts.get('update_fps', False)
        self.include_untested = opts.get('include_untested', False)
        self.output_dir       = opts.get('output_dir', os.getcwd())
        self.selected_groups  = opts.get('selected_groups', [])

        if not self.m3u_file or not self.selected_groups:
            QtWidgets.QMessageBox.warning(
                self.ui, 'Missing Settings',
                'Please select an M3U file and at least one group.'
            )
            return

        # parse groups
        with open(self.m3u_file, 'r', encoding='utf-8') as f:
            self.original_lines = f.readlines()
        raw_groups, self.categories = parse_groups(self.m3u_file)

        # build entry list
        self.group_entries = {}
        for grp, entries in raw_groups.items():
            self.group_entries[grp] = []
            for idx, e in enumerate(entries):
                match = CUID_RE.search(e.raw_inf)
                uid = match.group(1) if match else f"{grp}_{idx}"
                self.group_entries[grp].append({
                    'uid': uid,
                    'name': e.original_name,
                    'url':  e.url,
                    'group':grp,
                    'raw_inf': e.raw_inf,
                })

        # reset UI
        for tbl in (self.ui.tbl_working, self.ui.tbl_black_screen, self.ui.tbl_non_working):
            tbl.setRowCount(0)
        self.log_records = []
        self._refresh_console()

        # select & validate groups
        lookup = {k.lower(): k for k in self.group_entries}
        valid = []
        for sg in self.selected_groups:
            k = lookup.get(sg.lower())
            if k:
                valid.append(k)
            else:
                matches = [g for g in self.group_entries if sg.lower() in g.lower()]
                if matches:
                    valid += matches
                    self.log_signal.emit('working', f"[DEBUG] '{sg}' → {matches}")
                else:
                    self.log_signal.emit('error', f"No match for '{sg}'")
        if not valid:
            valid = list(self.group_entries.keys())
            self.log_signal.emit('working', "[DEBUG] defaulting to ALL groups")
        self.selected_groups = valid

        # flatten for checking
        self.entry_map = {
            e['uid']: e.copy()
            for grp in self.selected_groups
            for e   in self.group_entries[grp]
        }
        self.status_map = {}
        self.remaining  = len(self.entry_map)

        # launch tasks
        self.pool.setMaxThreadCount(self.workers)
        for entry in self.entry_map.values():
            task = CheckRunnable(entry, self.retries, self.timeout)
            task.log.connect(lambda lvl, m: self.log_signal.emit(lvl, m))
            task.result.connect(self.result_signal)
            self.pool.start(task)

        self.status_signal.emit(f"Queued {self.remaining} tasks", 3000)

    def _on_result(self, entry, status, res, fps):
        uid = entry['uid']
        self.status_map[uid] = status

        # update & annotate name
        name = entry['name']
        if status == 'UP':
            if self.update_quality and (ql := resolution_to_label(res)):
                name += f" {ql}"
            if self.update_fps and (fl := format_fps(fps)):
                name += f" {fl}"
        entry['name'] = name

        # insert into the appropriate table
        display = clean_name(name)
        tbl = {
            'UP':           self.ui.tbl_working,
            'BLACK_SCREEN': self.ui.tbl_black_screen
        }.get(status, self.ui.tbl_non_working)
        row = tbl.rowCount()
        tbl.insertRow(row)
        item = QtWidgets.QTableWidgetItem(display)
        item.setData(QtCore.Qt.UserRole, uid)
        tbl.setItem(row, 0, item)
        if tbl is self.ui.tbl_working:
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
            tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(fps))

        # log each result
        lvl = 'working' if status == 'UP' else 'error'
        self.log_signal.emit(lvl, f"[{status}] {name}")

        # when done, write outputs
        self.remaining -= 1
        if self.remaining == 0:
            threading.Thread(target=self._write_output, daemon=True).start()

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        self.ui.te_console.clear()
        buckets = {'working': [], 'info': [], 'error': []}
        for lvl, m in self.log_records:
            buckets.get(lvl, []).append(m)
        colors = {'working': 'green', 'info': 'orange', 'error': 'red'}
        for lvl in ('working', 'info', 'error'):
            cb = getattr(self.ui, f"cb_show_{lvl}", None)
            if cb and cb.isChecked():
                cur = self.ui.te_console.textCursor()
                for m in buckets[lvl]:
                    cur.movePosition(QTextCursor.End)
                    cur.insertHtml(f'<span style="color:{colors[lvl]};">{m}</span><br>')
                self.ui.te_console.setTextCursor(cur)

    def _toggle_pause(self):
        self.log_signal.emit('info', 'Pause/resume not supported with QRunnable')

    def stop_check(self):
        self.pool.clear()
        self.log_signal.emit('info', 'Stopping...')

    def _write_output(self):
        base = os.path.splitext(os.path.basename(self.m3u_file))[0]
        files = write_output_files(
            self.original_lines,
            self.entry_map,
            self.status_map,
            base,
            self.output_dir,
            split=self.split,
            update_quality=self.update_quality,
            update_fps=self.update_fps,
            include_untested=self.include_untested
        )
        if files:
            for p in files:
                self.log_signal.emit('info', f"Exported: {p}")
                self.status_signal.emit(f"Exported: {p}", 3000)
        else:
            self.log_signal.emit('info', "No M3U written")
            self.status_signal.emit("No M3U written", 3000)

    # Methods for MainWindow API
    def start(self): self._start_safe()
    def pause(self): self._toggle_pause()
    def stop(self):  self.stop_check()
