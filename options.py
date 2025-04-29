import os
from PyQt5 import QtWidgets
from parser import parse_groups
from dialogs import GroupSelectionDialog

class OptionsDialog(QtWidgets.QDialog):
    """
    Dialog for configuring M3U file, group selection,
    testing parameters, output modifiers, and output directory.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(450, 600)

        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        # M3U file selector
        m3u_h = QtWidgets.QHBoxLayout()
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U…")
        btn_browse.clicked.connect(self._on_browse_m3u)
        m3u_h.addWidget(self.le_m3u)
        m3u_h.addWidget(btn_browse)
        form.addRow("M3U File:", m3u_h)

        # Group selection
        self.btn_groups = QtWidgets.QPushButton("Select Groups")
        self.btn_groups.setEnabled(False)
        self.btn_groups.clicked.connect(self._on_select_groups)
        form.addRow("", self.btn_groups)

        # Testing parameters
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1, 100)
        self.sp_workers.setValue(30)
        form.addRow("Workers:", self.sp_workers)
        self.sp_retries = QtWidgets.QSpinBox()
        self.sp_retries.setRange(0, 10)
        self.sp_retries.setValue(3)
        form.addRow("Retries:", self.sp_retries)
        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(1, 60)
        self.sp_timeout.setValue(15)
        form.addRow("Timeout (s):", self.sp_timeout)

        # Output modifiers
        self.cb_split = QtWidgets.QCheckBox("Split into Files")
        form.addRow("", self.cb_split)
        self.cb_update_quality = QtWidgets.QCheckBox("Update Quality in Names")
        form.addRow("", self.cb_update_quality)
        self.cb_update_fps = QtWidgets.QCheckBox("Add FPS to Names")
        form.addRow("", self.cb_update_fps)
        self.cb_include_untested = QtWidgets.QCheckBox("Include Untested Channels")
        form.addRow("", self.cb_include_untested)

        # Output directory selector
        out_h = QtWidgets.QHBoxLayout()
        self.le_out = QtWidgets.QLineEdit(os.getcwd())
        btn_out = QtWidgets.QPushButton("Browse…")
        btn_out.clicked.connect(self._on_browse_out)
        out_h.addWidget(self.le_out)
        out_h.addWidget(btn_out)
        form.addRow("Output Dir:", out_h)

        layout.addLayout(form)
        layout.addStretch()

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_browse_m3u(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U Files (*.m3u)"
        )
        if not fn:
            return
        self.le_m3u.setText(fn)
        self.group_urls, self.categories = parse_groups(fn)
        self.selected_groups = []
        self.btn_groups.setEnabled(True)

    def _on_select_groups(self):
        dlg = GroupSelectionDialog(self.categories, self.group_urls, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _on_browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Folder"
        )
        if not d:
            return
        self.le_out.setText(d)
