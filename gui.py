import requests
import ffmpeg

def check_stream(url: str, timeout: int = 10) -> tuple[str, str, str]:
    """
    Return (status, resolution, bitrate) for a stream URL.
    Possible statuses: 'UP', 'BLACK_SCREEN', 'DOWN', 'ERROR'.
    """
    try:
        resp = requests.head(url, timeout=timeout)
        if resp.status_code != 200:
            return 'DOWN', '–', '–'
        try:
            info = ffmpeg.probe(url, select_streams='v', show_streams=True)
            stream = info['streams'][0]
            res = f"{stream['width']}×{stream['height']}"
            br = stream.get('bit_rate', '–')
            return 'UP', res, br
        except Exception:
            return 'BLACK_SCREEN', '–', '–'
    except Exception:
        return 'ERROR', '–', '–'


# gui.py
import sys
from queue import Queue
from PyQt5 import QtWidgets, QtGui, QtCore
from parser import parse_groups
from checker import check_stream

# Theme colors
DEEP_PURPLE = "#5b2fc9"
DARK_BG     = "#2b2b2b"
MID_BG      = "#3c3f41"
TEXT_LIGHT  = "#e0e0e0"
GREEN       = "#00c853"
RED         = "#d50000"
ORANGE      = "#ffab00"
HEADER_FONT = "Arial"

# Shared dark theme stylesheet
STYLE = f"""
QWidget {{ background: {DARK_BG}; color: {TEXT_LIGHT}; }}
QLabel {{ color: {TEXT_LIGHT}; }}
QLineEdit, QSpinBox, QComboBox {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; padding: 2px; }}
QPushButton {{ background: {DEEP_PURPLE}; color: white; border-radius: 4px; padding: 6px; }}
QPushButton:hover {{ background: #7e52e0; }}
QGroupBox {{ border: 2px solid {DEEP_PURPLE}; margin-top: 1em; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 4px; }}
QListWidget, QPlainTextEdit {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; padding-right: 20px; }}
QCheckBox {{ color: {TEXT_LIGHT}; }}
"""

class WorkerThread(QtCore.QThread):
    message = QtCore.pyqtSignal(str, str)
    result = QtCore.pyqtSignal(str, str)

    def __init__(self, queue, retries, timeout):
        super().__init__()
        self.queue = queue
        self.retries = retries
        self.timeout = timeout
        self._pause = threading.Event()
        self._pause.set()
        self._running = True

    def run(self):
        while self._running:
            self._pause.wait()
            try:
                url = self.queue.get(timeout=0.1)
            except:
                continue
            status = None
            for attempt in range(self.retries + 1):
                status, res, br = check_stream(url, timeout=self.timeout)
                if status == 'UP':
                    self.message.emit('success', f"{url} => OK [{res}, {br}]")
                    self.result.emit('Working', url)
                    break
                elif status == 'BLACK_SCREEN':
                    self.message.emit('info', f"{url} => Black Screen detected")
                    self.result.emit('Black Screen', url)
                    break
                else:
                    self.message.emit('info', f"{url} retry {attempt+1}/{self.retries}")
            else:
                self.message.emit('error', f"{url} => DOWN after {self.retries} retries")
                self.result.emit('Non Working', url)
            self.queue.task_done()

    def pause(self):
        self._pause.clear()

    def resume(self):
        self._pause.set()

    def stop(self):
        self._running = False
        self._pause.set()

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)
        self.setStyleSheet(STYLE)

        self.group_urls = {}
        self.selected = []
        self.queue = Queue()
        self.threads = []

        self._build_ui()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(10)

        hdr = QtWidgets.QLabel(
            f'<span style="font-family:{HEADER_FONT}; font-size:28pt; color:{TEXT_LIGHT}; font-weight:bold;">Don</span>'
            f'<span style="font-family:{HEADER_FONT}; font-size:28pt; color:{DEEP_PURPLE}; font-weight:bold;">TV</span> IPTV Checker'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        hdr.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(hdr)

        # Parameters
        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel("Workers:"))
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,100); self.sp_workers.setValue(10)
        params.addWidget(self.sp_workers)
        params.addWidget(QtWidgets.QLabel("Timeout:"))
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10)
        params.addWidget(self.sp_timeout)
        params.addWidget(QtWidgets.QLabel("Retries:"))
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(0,5); self.sp_retries.setValue(2)
        params.addWidget(self.sp_retries)
        layout.addLayout(params)

        # Control buttons
        ctrls = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_start.clicked.connect(self.start_check)
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_pause.clicked.connect(self.pause_check)
        self.btn_stop = QtWidgets.QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_check)
        ctrls.addWidget(self.btn_start)
        ctrls.addWidget(self.btn_pause)
        ctrls.addWidget(self.btn_stop)
        layout.addLayout(ctrls)

        # Result panes
        panes = QtWidgets.QHBoxLayout()
        box_w, self.lw_working = self._make_listbox("Working")
        box_b, self.lw_black   = self._make_listbox("Black Screen")
        box_n, self.lw_fail    = self._make_listbox("Non Working")
        panes.addWidget(box_w)
        panes.addWidget(box_b)
        panes.addWidget(box_n)
        layout.addLayout(panes)

        # Console & filters
        console_box = QtWidgets.QGroupBox("Console")
        vb = QtWidgets.QVBoxLayout(console_box)
        hf = QtWidgets.QHBoxLayout()
        self.cb_ok   = QtWidgets.QCheckBox("Show OK");   self.cb_ok.setChecked(True)
        self.cb_info = QtWidgets.QCheckBox("Show Info"); self.cb_info.setChecked(True)
        self.cb_fail = QtWidgets.QCheckBox("Show Fail"); self.cb_fail.setChecked(True)
        hf.addWidget(self.cb_ok); hf.addWidget(self.cb_info); hf.addWidget(self.cb_fail)
        vb.addLayout(hf)
        self.console = QtWidgets.QPlainTextEdit(); self.console.setReadOnly(True)
        vb.addWidget(self.console)
        layout.addWidget(console_box)

        # File & group selection
        top = QtWidgets.QHBoxLayout()
        self.le_file = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U")
        btn_browse.clicked.connect(self._browse_file)
        btn_select = QtWidgets.QPushButton("Select Groups")
        btn_select.clicked.connect(self._select_groups)
        top.addWidget(self.le_file); top.addWidget(btn_browse); top.addWidget(btn_select)
        layout.insertLayout(1, top)

        self.setCentralWidget(central)

    def _make_listbox(self, title):
        box = QtWidgets.QGroupBox(title)
        v = QtWidgets.QVBoxLayout(box)
        lw = QtWidgets.QListWidget()
        v.addWidget(lw)
        return box, lw

    def _browse_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U Files (*.m3u)"
        )
        if path:
            self.le_file.setText(path)

    def _select_groups(self):
        from qt_helpers import GroupSelectionDialog
        gu, cats = parse_groups(self.le_file.text())
        self.group_urls = gu
        dlg = GroupSelectionDialog(cats, gu, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected = dlg.selected_groups()

    def log(self, level, text):
        color = {'success':GREEN, 'info':ORANGE, 'error':RED}.get(level, TEXT_LIGHT)
        if level=='success' and not self.cb_ok.isChecked(): return
        if level=='info'    and not self.cb_info.isChecked(): return
        if level=='error'   and not self.cb_fail.isChecked(): return
        self.console.appendHtml(f'<span style="color:{color};">{text}</span>')

    def start_check(self):
        # clear previous
        self.lw_working.clear(); self.lw_black.clear(); self.lw_fail.clear(); self.console.clear()
        for url in sum((self.group_urls[g] for g in self.selected), []):
            self.queue.put(url)
        self.stop_check()
        for _ in range(self.sp_workers.value()):
            t = WorkerThread(self.queue, self.sp_retries.value(), self.sp_timeout.value())
            t.message.connect(self.log)
            t.result.connect(self._add_result)
            t.start()
            self.threads.append(t)

    def pause_check(self):
        for t in self.threads: t.pause()

    def stop_check(self):
        for t in self.threads: t.stop()
        self.threads = []

    def _add_result(self, category, url):
        if category=='Working': self.lw_working.addItem(url)
        elif category=='Black Screen': self.lw_black.addItem(url)
        else: self.lw_fail.addItem(url)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    window = IPTVChecker()
    window.show()
    sys.exit(app.exec_())
