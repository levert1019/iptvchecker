import os
from PyQt5 import QtWidgets, QtCore

class OptionsDialog(QtWidgets.QDialog):
    """
    Dialog for setting M3U file, group selection, testing options,
    output modifiers, and output directory.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(450, 600)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        # M3U file selector
        m3u_h = QtWidgets.QHBoxLayout()
        self.le_m3u = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U…")
        btn_browse.clicked.connect(parent._on_browse_m3u)
        m3u_h.addWidget(self.le_m3u)
        m3u_h.addWidget(btn_browse)
        form.addRow("M3U File:", m3u_h)

        # Group selection
        self.btn_groups = QtWidgets.QPushButton("Select Groups")
        self.btn_groups.clicked.connect(parent._on_select_groups)
        form.addRow("", self.btn_groups)

        # Testing options
        self.sp_workers = QtWidgets.QSpinBox()
        self.sp_workers.setRange(1, 100)
        form.addRow("Workers:", self.sp_workers)

        self.sp_retries = QtWidgets.QSpinBox()
        self.sp_retries.setRange(0, 10)
        form.addRow("Retries:", self.sp_retries)

        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(1, 60)
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
        self.le_out = QtWidgets.QLineEdit()
        btn_out = QtWidgets.QPushButton("Browse…")
        btn_out.clicked.connect(parent._on_browse_out)
        out_h.addWidget(self.le_out)
        out_h.addWidget(btn_out)
        form.addRow("Output Dir:", out_h)

        layout.addLayout(form)
        layout.addStretch()

        # OK/Cancel buttons
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
