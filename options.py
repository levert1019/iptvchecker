# options.py

import os
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from dialogs import GroupSelectionDialog

class OptionsDialog(QtWidgets.QDialog):
    """
    Dialog for selecting M3U file, categorizing groups, worker settings, and output options.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(900, 600)
        self.group_urls = {}  # group-title -> list of entries
        self.selected_groups = []
        self._apply_dark_theme()
        self._init_ui()

    def _apply_dark_theme(self):
        # Fusion style + global dark stylesheet
        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet("""
            QDialog { background-color: #2b2b2b; }
            QLabel, QCheckBox { color: #e0e0e0; }
            QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #3c3f41; color: #e0e0e0; border: 1px solid #555555; border-radius: 3px; padding: 2px; }
            QListWidget { background-color: #3c3f41; color: #e0e0e0; border: none; }
            QPushButton { background-color: #5b2fc9; color: white; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #7d4ce7; }
        """)

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Form: M3U, workers, retries, timeout, output options ---
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
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,50); self.sp_workers.setValue(5)
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(0,10); self.sp_retries.setValue(2)
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10)
        form.addRow("Workers:", self.sp_workers)
        form.addRow("Retries:", self.sp_retries)
        form.addRow("Timeout (s):", self.sp_timeout)

        # Flags
        self.cb_split = QtWidgets.QCheckBox("Split into separate files")
        self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Name")
        self.cb_update_fps = QtWidgets.QCheckBox("Update FPS in Name")
        self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels")
        form.addRow(self.cb_split)
        form.addRow(self.cb_update_quality)
        form.addRow(self.cb_update_fps)
        form.addRow(self.cb_include_untested)

        # Output directory picker
        self.le_out = QtWidgets.QLineEdit(os.getcwd())
        btn_out = QtWidgets.QPushButton("Browse Output...")
        btn_out.clicked.connect(self._browse_out)
        h_out = QtWidgets.QHBoxLayout()
        h_out.addWidget(self.le_out)
        h_out.addWidget(btn_out)
        form.addRow("Output Dir:", h_out)

        main_layout.addLayout(form)

        # --- Group selection ---
        self.btn_groups = QtWidgets.QPushButton("Select Groups...")
        self.btn_groups.setEnabled(False)
        self.btn_groups.clicked.connect(self._open_group_selector)
        main_layout.addWidget(self.btn_groups)

        # --- Dialog buttons ---
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def _browse_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U files (*.m3u *.m3u8);;All files (*)"
        )
        if path:
            self.le_m3u.setText(path)
            self.group_urls, _ = parse_groups(path)
            self.btn_groups.setEnabled(True)

    def _open_group_selector(self):
        # Independent classification: group can appear in multiple categories
        live, movies, series = [], [], []
        for grp, entries in self.group_urls.items():
            urls = [e['url'].lower() for e in entries]
            if any('movie' not in u and 'series' not in u for u in urls):
                live.append(grp)
            if any('movie' in u for u in urls):
                movies.append(grp)
            if any('series' in u for u in urls):
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

    def _on_accept(self):
        self.accept()
