import os
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from styles import STYLE_SHEET

class OptionsDialog(QtWidgets.QDialog):
    def __init__(self, categories, group_entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(800, 600)

        # Data
        self.categories = categories or {}
        self.group_entries = group_entries or {}
        self.selected_groups = list(getattr(self, 'selected_groups', []))

        # Apply theme
        self.setStyleSheet(STYLE_SHEET)
        self._build_ui()

    def _build_ui(self):
        main_v = QtWidgets.QVBoxLayout(self)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(20)

        # Main Options header
        lbl_main = QtWidgets.QLabel("<b>Main Options</b>")
        main_v.addWidget(lbl_main)

        grp_main = QtWidgets.QGroupBox()
        v_main = QtWidgets.QGridLayout(grp_main)
        v_main.setColumnStretch(1, 1)

        # M3U File
        v_main.addWidget(QtWidgets.QLabel("M3U File:"), 0, 0)
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_m3u)
        h_m3u = QtWidgets.QHBoxLayout()
        h_m3u.addWidget(self.le_m3u)
        h_m3u.addWidget(btn_browse)
        v_main.addLayout(h_m3u, 0, 1)

        # Groups
        v_main.addWidget(QtWidgets.QLabel("Groups:"), 1, 0)
        self.btn_groups = QtWidgets.QPushButton("Select Groups...")
        self.btn_groups.setEnabled(bool(self.categories))
        self.btn_groups.clicked.connect(self._select_groups)
        v_main.addWidget(self.btn_groups, 1, 1)

        # Output Directory
        v_main.addWidget(QtWidgets.QLabel("Output Directory:"), 2, 0)
        self.le_out = QtWidgets.QLineEdit()
        btn_out = QtWidgets.QPushButton("Browse...")
        btn_out.clicked.connect(self._browse_out)
        h_out = QtWidgets.QHBoxLayout()
        h_out.addWidget(self.le_out)
        h_out.addWidget(btn_out)
        v_main.addLayout(h_out, 2, 1)

        main_v.addWidget(grp_main)

        # IPTV Checker Settings header
        lbl_chk = QtWidgets.QLabel("<b>IPTV Checker Settings</b>")
        main_v.addWidget(lbl_chk)

        grp_chk = QtWidgets.QGroupBox()
        v_chk = QtWidgets.QGridLayout(grp_chk)
        v_chk.setColumnStretch(1, 1)

        # Workers
        v_chk.addWidget(QtWidgets.QLabel("Workers:"), 0, 0)
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1, 50)
        v_chk.addWidget(self.sp_workers, 0, 1)

        # Retries
        v_chk.addWidget(QtWidgets.QLabel("Retries:"), 1, 0)
        self.sp_retries = QtWidgets.QSpinBox()
        self.sp_retries.setRange(0, 10)
        v_chk.addWidget(self.sp_retries, 1, 1)

        # Timeout
        v_chk.addWidget(QtWidgets.QLabel("Timeout (s):"), 2, 0)
        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(1, 120)
        v_chk.addWidget(self.sp_timeout, 2, 1)

        # Checkboxes
        self.cb_split = QtWidgets.QCheckBox("Split output into separate files")
        self.cb_update_quality = QtWidgets.QCheckBox("Update resolution label")
        self.cb_update_fps = QtWidgets.QCheckBox("Update FPS label")
        self.cb_include_untested = QtWidgets.QCheckBox("Include untested entries")
        v_chk.addWidget(self.cb_split, 3, 0, 1, 2)
        v_chk.addWidget(self.cb_update_quality, 4, 0, 1, 2)
        v_chk.addWidget(self.cb_update_fps, 5, 0, 1, 2)
        v_chk.addWidget(self.cb_include_untested, 6, 0, 1, 2)

        main_v.addWidget(grp_chk)

        # Dialog buttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_v.addWidget(btns)

    def _browse_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", os.getcwd(), "M3U Files (*.m3u *.m3u8)")
        if path:
            self.le_m3u.setText(path)
            # reload categories and entries
            self.group_entries, self.categories = parse_groups(path)
            self.btn_groups.setEnabled(True)

    def _select_groups(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Select Groups")
        dlg.resize(900, 600)
        v_main = QtWidgets.QVBoxLayout(dlg)
        h = QtWidgets.QHBoxLayout()

        # For each category, create a groupbox
        list_widgets = {}
        for cat, groups in self.categories.items():
            grp_box = QtWidgets.QGroupBox(cat)
            grp_box.setStyleSheet("QGroupBox { font-weight: bold; color: white; background-color: #5b2fc9; }")
            v = QtWidgets.QVBoxLayout(grp_box)
            # Select/Unselect All button
            btn_all = QtWidgets.QPushButton("Select/Unselect All")
            def make_toggle(lw):
                def toggle():
                    all_checked = all(lw.item(i).checkState() == QtCore.Qt.Checked for i in range(lw.count()))
                    for i in range(lw.count()): lw.item(i).setCheckState(QtCore.Qt.Unchecked if all_checked else QtCore.Qt.Checked)
                return toggle
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            def make_menu(lw):
                def menu(pos):
                    m = QtWidgets.QMenu()
                    m.addAction("Check All", lambda: [lw.item(i).setCheckState(QtCore.Qt.Checked) for i in range(lw.count())])
                    m.addAction("Uncheck All", lambda: [lw.item(i).setCheckState(QtCore.Qt.Unchecked) for i in range(lw.count())])
                    m.addAction("Check Selected", lambda: [item.setCheckState(QtCore.Qt.Checked) for item in lw.selectedItems()])
                    m.addAction("Uncheck Selected", lambda: [item.setCheckState(QtCore.Qt.Unchecked) for item in lw.selectedItems()])
                    m.exec_(lw.mapToGlobal(pos))
                return menu
            btn_all.clicked.connect(make_toggle(lw))
            lw.customContextMenuRequested.connect(make_menu(lw))
            for g in sorted(groups):
                item = QtWidgets.QListWidgetItem(g)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Checked if g in self.selected_groups else QtCore.Qt.Unchecked)
                lw.addItem(item)
            v.addWidget(btn_all)
            v.addWidget(lw)
            h.addWidget(grp_box)
            list_widgets[cat] = lw

        v_main.addLayout(h)
        # Ok/Cancel
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v_main.addWidget(btns)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            # collect checked
            sel = []
            for lw in list_widgets.values():
                for i in range(lw.count()):
                    if lw.item(i).checkState() == QtCore.Qt.Checked:
                        sel.append(lw.item(i).text())
            self.selected_groups = sel

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory", os.getcwd())
        if path:
            self.le_out.setText(path)

    def get_options(self):
        return {
            "m3u_file": self.le_m3u.text(),
            "workers": self.sp_workers.value(),
            "retries": self.sp_retries.value(),
            "timeout": self.sp_timeout.value(),
            "split": self.cb_split.isChecked(),
            "update_quality": self.cb_update_quality.isChecked(),
            "update_fps": self.cb_update_fps.isChecked(),
            "include_untested": self.cb_include_untested.isChecked(),
            "output_dir": self.le_out.text(),
            "selected_groups": self.selected_groups
        }
