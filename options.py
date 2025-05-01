# options.py

import os
from PyQt5 import QtWidgets, QtGui, QtCore
from parser import parse_groups
from dialogs import GroupSelectionDialog

class OptionsDialog(QtWidgets.QDialog):
    """
    Options dialog for IPTV Checker.
    """
    def __init__(self, categories=None, group_urls=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(600, 450)

        # Initial state
        self.m3u_file = ""
        # group_entries maps group-title -> list of entry dicts
        self.group_entries = group_urls or {}
        self.categories   = categories    or {}
        self.selected_groups = []

        # IPTV options defaults
        self.workers          = 5
        self.retries          = 2
        self.timeout          = 10
        self.split            = False
        self.update_quality   = False
        self.update_fps       = False
        self.include_untested = False
        self.output_dir       = os.getcwd()

        self._init_ui()
        self._apply_dark_theme()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        # M3U file picker
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U…")
        btn_browse.clicked.connect(self._browse_m3u)
        h_m3u = QtWidgets.QHBoxLayout()
        h_m3u.addWidget(self.le_m3u)
        h_m3u.addWidget(btn_browse)
        form.addRow("M3U File:", h_m3u)

        # Worker / retries / timeout
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1, 50)
        self.sp_workers.setValue(self.workers)
        self.sp_retries = QtWidgets.QSpinBox()
        self.sp_retries.setRange(0, 10)
        self.sp_retries.setValue(self.retries)
        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(1, 60)
        self.sp_timeout.setValue(self.timeout)
        form.addRow("Workers:", self.sp_workers)
        form.addRow("Retries:", self.sp_retries)
        form.addRow("Timeout (s):", self.sp_timeout)

        # Feature checkboxes
        self.cb_split = QtWidgets.QCheckBox("Split into separate files")
        self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Name")
        self.cb_update_fps = QtWidgets.QCheckBox("Update FPS in Name")
        self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels")
        form.addRow(self.cb_split)
        form.addRow(self.cb_update_quality)
        form.addRow(self.cb_update_fps)
        form.addRow(self.cb_include_untested)

        # Output directory
        self.le_out = QtWidgets.QLineEdit(self.output_dir)
        btn_out = QtWidgets.QPushButton("Browse Output…")
        btn_out.clicked.connect(self._browse_out)
        h_out = QtWidgets.QHBoxLayout()
        h_out.addWidget(self.le_out)
        h_out.addWidget(btn_out)
        form.addRow("Output Dir:", h_out)

        layout.addLayout(form)

        # Always-visible Select Groups button
        self.btn_groups = QtWidgets.QPushButton("Select Groups…")
        self.btn_groups.clicked.connect(self._open_group_selector)
        layout.addWidget(self.btn_groups)

        layout.addStretch()

        # OK / Cancel
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _apply_dark_theme(self):
        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#222222"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#2e2e2e"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#9b2cfc"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#9b2cfc"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#000000"))
        QtWidgets.QApplication.instance().setPalette(pal)

    def _browse_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U files (*.m3u *.m3u8);;All files (*)"
        )
        if not path:
            return
        self.le_m3u.setText(path)
        self.m3u_file = path
        # Immediately parse groups
        self.group_entries, self.categories = parse_groups(path)

    def _open_group_selector(self):
        if not self.m3u_file or not os.path.isfile(self.m3u_file):
            QtWidgets.QMessageBox.warning(self, "No M3U File",
                                          "Please select a valid M3U file first.")
            return

        # Ensure group_entries/categories are fresh
        self.group_entries, self.categories = parse_groups(self.m3u_file)

        # Build Live/Movie/Series lists
        live, movies, series = [], [], []
        for grp, entries in self.group_entries.items():
            name_l = grp.lower()
            urls_l = [e['url'].lower() for e in entries]
            is_movie  = 'movie'  in name_l or any('movie'  in u for u in urls_l)
            is_series = 'series' in name_l or any('series' in u for u in urls_l)
            is_live   = 'live'   in name_l or any('live'   in u for u in urls_l) or not (is_movie or is_series)
            if is_live:   live.append(grp)
            if is_movie:  movies.append(grp)
            if is_series: series.append(grp)

        cats = {'Live': live, 'Movie': movies, 'Series': series}
        dlg = GroupSelectionDialog(cats, self.group_entries, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.le_out.text()
        )
        if path:
            self.le_out.setText(path)

    def get_options(self):
        return {
            "m3u_file":         self.m3u_file,
            "workers":          self.sp_workers.value(),
            "retries":          self.sp_retries.value(),
            "timeout":          self.sp_timeout.value(),
            "split":            self.cb_split.isChecked(),
            "update_quality":   self.cb_update_quality.isChecked(),
            "update_fps":       self.cb_update_fps.isChecked(),
            "include_untested": self.cb_include_untested.isChecked(),
            "output_dir":       self.le_out.text(),
            "selected_groups":  self.selected_groups
        }
