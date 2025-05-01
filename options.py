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
        self.resize(800, 600)
        self.group_urls = {}       # group-title -> list of entries
        self.selected_groups = []
        # UI elements per category
        self.list_widgets = {}
        self._init_ui()

    def _init_ui(self):
        # Dark theme
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; }
            QLabel, QCheckBox { color: #e0e0e0; }
            QListWidget { background-color: #3c3f41; color: #e0e0e0; }
            QPushButton { background-color: #5b2fc9; color: white; border-radius: 4px; padding: 4px; }
            QPushButton:hover { background-color: #7d4ce7; }
            QTabWidget::pane { border: 1px solid #444; }
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        # M3U file picker
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U...")
        btn_browse.clicked.connect(self._browse_m3u)
        h_m3u = QtWidgets.QHBoxLayout()
        h_m3u.addWidget(self.le_m3u)
        h_m3u.addWidget(btn_browse)
        form.addRow("M3U File:", h_m3u)

        # Worker settings
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,50); self.sp_workers.setValue(5)
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(0,10); self.sp_retries.setValue(2)
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10)
        form.addRow("Workers:", self.sp_workers)
        form.addRow("Retries:", self.sp_retries)
        form.addRow("Timeout (s):", self.sp_timeout)

        # Output options
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

        # Select Groups Button
        self.btn_groups = QtWidgets.QPushButton("Select Groups...")
        self.btn_groups.setEnabled(False)
        self.btn_groups.clicked.connect(self._open_group_selector)
        main_layout.addWidget(self.btn_groups)

        # Dialog buttons
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
        # Categorize groups by URL content
        live, movies, series = [], [], []
        for grp, entries in self.group_urls.items():
            urls = [e['url'].lower() for e in entries]
            if any('series' in u for u in urls):
                series.append(grp)
            elif any('movie' in u for u in urls):
                movies.append(grp)
            else:
                live.append(grp)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Select Groups")
        dlg.resize(700, 500)
        dlg.setStyleSheet(self.styleSheet())

        top_layout = QtWidgets.QVBoxLayout(dlg)
        tabs = QtWidgets.QTabWidget()
        tabs.setTabPosition(QtWidgets.QTabWidget.North)
        tabs.setDocumentMode(True)
        categories = {'Live': live, 'Movies': movies, 'Series': series}

        # Build each tab
        for cat, groups in categories.items():
            page = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(page)
            # Buttons: Select All / Deselect All
            btn_h = QtWidgets.QHBoxLayout()
            btn_all = QtWidgets.QPushButton("Select All")
            btn_none = QtWidgets.QPushButton("Deselect All")
            btn_h.addWidget(btn_all)
            btn_h.addWidget(btn_none)
            v.addLayout(btn_h)
            # List
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(lambda pos, lw=lw: self._show_context_menu(lw, pos))
            for grp in groups:
                itm = QtWidgets.QListWidgetItem(grp)
                itm.setFlags(itm.flags() | QtCore.Qt.ItemIsUserCheckable)
                itm.setCheckState(QtCore.Qt.Checked if grp in self.selected_groups else QtCore.Qt.Unchecked)
                lw.addItem(itm)
            btn_all.clicked.connect(lambda _, lw=lw: self._set_all(lw, QtCore.Qt.Checked))
            btn_none.clicked.connect(lambda _, lw=lw: self._set_all(lw, QtCore.Qt.Unchecked))
            v.addWidget(lw)
            tabs.addTab(page, cat)
            self.list_widgets[cat] = lw

        top_layout.addWidget(tabs)
        # OK/Cancel
        btns2 = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns2.accepted.connect(dlg.accept)
        btns2.rejected.connect(dlg.reject)
        top_layout.addWidget(btns2)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            sel = []
            for lw in self.list_widgets.values():
                for i in range(lw.count()):
                    itm = lw.item(i)
                    if itm.checkState() == QtCore.Qt.Checked:
                        sel.append(itm.text())
            self.selected_groups = sel

    def _set_all(self, lw, state):
        for i in range(lw.count()):
            lw.item(i).setCheckState(state)

    def _show_context_menu(self, lw, pos):
        menu = QtWidgets.QMenu()
        act_check = menu.addAction("Check Selected")
        act_uncheck = menu.addAction("Uncheck Selected")
        action = menu.exec_(lw.mapToGlobal(pos))
        if action == act_check:
            for itm in lw.selectedItems(): itm.setCheckState(QtCore.Qt.Checked)
        elif action == act_uncheck:
            for itm in lw.selectedItems(): itm.setCheckState(QtCore.Qt.Unchecked)

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory", self.le_out.text())
        if path:
            self.le_out.setText(path)

    def _on_accept(self):
        self.accept()
