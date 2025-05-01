import os
from PyQt5 import QtWidgets, QtGui, QtCore
from parser import parse_groups
from dialogs import GroupSelectionDialog
import playlist_sorter

# Configuration stored in project folder\
CONFIG_FILE = os.path.join(os.getcwd(), "dontvconfig.txt")

class OptionsDialog(QtWidgets.QDialog):
    """
    Main options dialog for DonTV scripts (IPTV Checker, Playlist Sorter, etc.).
    Includes IPTV options plus Playlist Sorter toggle, TMDB API key, and group selector.
    """
    def __init__(self, categories=None, group_urls=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(600, 550)

        # Load TMDB API key and auto-enable sorter if present
        self.api_key = ""
        self._load_api_key()
        self.enable_sorter = bool(self.api_key)

        # IPTV settings
        self.m3u_file = ""
        self.categories = categories or {}
        self.group_urls = group_urls or {}
        self.selected_groups = []
        self.workers = 5
        self.retries = 2
        self.timeout = 10
        self.split = False
        self.update_quality = False
        self.update_fps = False
        self.include_untested = False

        self._init_ui()
        self._apply_dark_theme()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # Form for file/workers/retries/timeout and flags
        form = QtWidgets.QFormLayout()

        # M3U file picker
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U...")
        btn_browse.clicked.connect(self._browse_m3u)
        h_m3u = QtWidgets.QHBoxLayout()
        h_m3u.addWidget(self.le_m3u)
        h_m3u.addWidget(btn_browse)
        form.addRow("M3U File:", h_m3u)

        # Workers / Retries / Timeout
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1,50)
        self.sp_workers.setValue(self.workers)
        self.sp_retries = QtWidgets.QSpinBox()
        self.sp_retries.setRange(0,10)
        self.sp_retries.setValue(self.retries)
        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(1,60)
        self.sp_timeout.setValue(self.timeout)
        form.addRow("Workers:", self.sp_workers)
        form.addRow("Retries:", self.sp_retries)
        form.addRow("Timeout (s):", self.sp_timeout)

        # IPTV flags
        self.cb_split = QtWidgets.QCheckBox("Split into separate files")
        self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Name")
        self.cb_update_fps = QtWidgets.QCheckBox("Update FPS in Name")
        self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels")
        form.addRow(self.cb_split)
        form.addRow(self.cb_update_quality)
        form.addRow(self.cb_update_fps)
        form.addRow(self.cb_include_untested)

        # Playlist Sorter toggle
        self.cb_sorter = QtWidgets.QCheckBox("Enable Playlist Sorter")
        self.cb_sorter.setChecked(self.enable_sorter)
        self.cb_sorter.stateChanged.connect(lambda s: setattr(self, 'enable_sorter', s == QtCore.Qt.Checked))
        form.addRow(self.cb_sorter)

        # TMDB API key entry
        self.le_api = QtWidgets.QLineEdit(self.api_key)
        btn_save_api = QtWidgets.QPushButton("Save TMDB API Key")
        btn_save_api.clicked.connect(self._save_api_key)
        h_api = QtWidgets.QHBoxLayout()
        h_api.addWidget(self.le_api)
        h_api.addWidget(btn_save_api)
        form.addRow("TMDB API Key:", h_api)

        main_layout.addLayout(form)

        # Always visible Select Groups button
        self.btn_groups = QtWidgets.QPushButton("Select Groups...")
        self.btn_groups.clicked.connect(self._open_group_selector)
        main_layout.addWidget(self.btn_groups)

        # Output directory picker
        h_out = QtWidgets.QHBoxLayout()
        self.le_out = QtWidgets.QLineEdit(os.getcwd())
        btn_out = QtWidgets.QPushButton("Browse Output...")
        btn_out.clicked.connect(self._browse_out)
        h_out.addWidget(self.le_out)
        h_out.addWidget(btn_out)
        main_layout.addLayout(h_out)

        main_layout.addStretch()

        # OK / Cancel buttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def _apply_dark_theme(self):
        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#2b2b2b"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#e0e0e0"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#3c3f41"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#e0e0e0"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#5b2fc9"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#5b2fc9"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#000000"))
        QtWidgets.QApplication.instance().setPalette(pal)

    def _browse_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U files (*.m3u *.m3u8);;All files (*)"
        )
        if path:
            self.le_m3u.setText(path)
            self.m3u_file = path
            self.group_urls, self.categories = parse_groups(path)

    def _open_group_selector(self):
        if self.m3u_file and not self.categories:
            self.group_urls, self.categories = parse_groups(self.m3u_file)
        live, movies, series = [], [], []
        for grp, entries in self.group_urls.items():
            lower = grp.lower()
            urls = [e['url'].lower() for e in entries]
            is_movie = 'movie' in lower or any('movie' in u for u in urls)
            is_series = 'series' in lower or any('series' in u for u in urls)
            is_live = 'live' in lower or any('live' in u for u in urls) or not (is_movie or is_series)
            if is_live:
                live.append(grp)
            if is_movie:
                movies.append(grp)
            if is_series:
                series.append(grp)
        categories = {'Live': live, 'Movie': movies, 'Series': series}
        dlg = GroupSelectionDialog(categories, self.group_urls, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.le_out.text()
        )
        if path:
            self.le_out.setText(path)

    def _load_api_key(self):
        self.api_key = ""
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                for line in f:
                    if line.startswith('TMDB_API_KEY='):
                        self.api_key = line.split('=',1)[1].strip()
                        break

    def _save_api_key(self):
        self.api_key = self.le_api.text().strip()
        lines = []
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                lines = f.readlines()
        with open(CONFIG_FILE, 'w') as f:
            written = False
            for ln in lines:
                if ln.startswith('TMDB_API_KEY='):
                    f.write(f"TMDB_API_KEY={self.api_key}\n")
                    written = True
                else:
                    f.write(ln)
            if not written:
                f.write(f"TMDB_API_KEY={self.api_key}\n")
        QtWidgets.QMessageBox.information(self, "Saved", "TMDB API key saved to dontvconfig.txt")

    def get_options(self):
        return {
            'm3u_file': self.m3u_file,
            'workers': self.sp_workers.value(),
            'retries': self.sp_retries.value(),
            'timeout': self.sp_timeout.value(),
            'split': self.cb_split.isChecked(),
            'update_quality': self.cb_update_quality.isChecked(),
            'update_fps': self.cb_update_fps.isChecked(),
            'include_untested': self.cb_include_untested.isChecked(),
            'enable_sorter': self.enable_sorter,
            'tmdb_api_key': self.api_key,
            'output_dir': self.le_out.text(),
            'selected_groups': self.selected_groups
        }