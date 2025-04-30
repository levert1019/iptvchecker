import os
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups

class OptionsDialog(QtWidgets.QDialog):
    """
    Dialog for selecting M3U file, categorizing groups, worker settings, and output options.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        # M3U file picker
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_m3u)
        h_m3u = QtWidgets.QHBoxLayout()
        h_m3u.addWidget(self.le_m3u)
        h_m3u.addWidget(btn_browse)
        form.addRow("M3U File:", h_m3u)

        # Select Groups button
        self.btn_groups = QtWidgets.QPushButton("Select Groups...")
        self.btn_groups.setEnabled(False)
        self.btn_groups.clicked.connect(self._open_group_selector)
        form.addRow("Groups:", self.btn_groups)

        # Worker settings
        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1,50); self.sp_workers.setValue(5)
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(0,10); self.sp_retries.setValue(2)
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,60); self.sp_timeout.setValue(10)
        form.addRow("Workers:", self.sp_workers)
        form.addRow("Retries:", self.sp_retries)
        form.addRow("Timeout (s):", self.sp_timeout)

        # Output options
        self.cb_split = QtWidgets.QCheckBox("Split into files")
        self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Name")
        self.cb_update_fps = QtWidgets.QCheckBox("Update FPS in Name")
        self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels")
        form.addRow(self.cb_split)
        form.addRow(self.cb_update_quality)
        form.addRow(self.cb_update_fps)
        form.addRow(self.cb_include_untested)

        # Output directory picker
        self.le_out = QtWidgets.QLineEdit(os.getcwd())
        btn_out = QtWidgets.QPushButton("Browse...")
        btn_out.clicked.connect(self._browse_out)
        h_out = QtWidgets.QHBoxLayout()
        h_out.addWidget(self.le_out)
        h_out.addWidget(btn_out)
        form.addRow("Output Dir:", h_out)

        layout.addLayout(form)

        # OK/Cancel
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U files (*.m3u *.m3u8);;All files (*)"
        )
        if path:
            self.le_m3u.setText(path)
            self.group_urls, self.categories = parse_groups(path)
            self.btn_groups.setEnabled(True)

    def _open_group_selector(self):
        # categorize groups by URL content
        live, movies, series = [], [], []
        for grp, entries in self.group_urls.items():
            urls = [e['url'].lower() for e in entries]
            if any('series' in u for u in urls): series.append(grp)
            elif any('movie' in u for u in urls): movies.append(grp)
            else: live.append(grp)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Select Groups")
        dlg.resize(400,500)
        tabs = QtWidgets.QTabWidget(dlg)
        lists = {}
        for title, group_list in [('Live', live), ('Movies', movies), ('Series', series)]:
            page = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(page)
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            for grp in group_list:
                itm = QtWidgets.QListWidgetItem(grp)
                itm.setFlags(itm.flags() | QtCore.Qt.ItemIsUserCheckable)
                state = QtCore.Qt.Checked if grp in self.selected_groups else QtCore.Qt.Unchecked
                itm.setCheckState(state)
                lw.addItem(itm)
            v.addWidget(lw)
            tabs.addTab(page, title)
            lists[title] = lw
        dlg_layout = QtWidgets.QVBoxLayout(dlg)
        dlg_layout.addWidget(tabs)
        btns2 = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns2.accepted.connect(dlg.accept)
        btns2.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns2)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            sel = []
            for lw in lists.values():
                for i in range(lw.count()):
                    itm = lw.item(i)
                    if itm.checkState() == QtCore.Qt.Checked:
                        sel.append(itm.text())
            self.selected_groups = sel

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory", self.le_out.text())
        if path:
            self.le_out.setText(path)

    def _on_accept(self):
        self.accept()
