from PyQt5 import QtWidgets, QtCore

class SorterUI(QtWidgets.QWidget):
    """
    UI definition for the Playlist Sorter page.
    Exposes:
      - le_sort_m3u       (QLineEdit)
      - btn_browse        (QPushButton)
      - tree_groups       (QTreeWidget)
      - cb_alpha          (QCheckBox)
      - btn_generate      (QPushButton)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # Header (rich text)
        hdr = QtWidgets.QLabel()
        hdr.setTextFormat(QtCore.Qt.RichText)
        hdr.setText(
            '<span style="font-size:24pt; color:#FFFFFF; font-weight:bold;">Don</span>'
            '<span style="font-size:24pt; color:#5b2fc9; font-weight:bold;">TV</span>'
            '<span style="font-size:18pt; color:#FFFFFF; font-weight:bold;"> Playlist Sorter</span>'
        )
        hdr.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hdr)

        # File selector row
        file_h = QtWidgets.QHBoxLayout()
        self.le_sort_m3u = QtWidgets.QLineEdit()
        self.btn_browse  = QtWidgets.QPushButton("Browse…")
        file_h.addWidget(self.le_sort_m3u)
        file_h.addWidget(self.btn_browse)
        layout.addLayout(file_h)

        # Draggable group-order tree
        self.tree_groups = QtWidgets.QTreeWidget()
        self.tree_groups.setHeaderLabels(["Group Name"])
        self.tree_groups.setDragDropMode(
            QtWidgets.QAbstractItemView.InternalMove
        )
        layout.addWidget(self.tree_groups, 1)

        # Sort options
        opts_h = QtWidgets.QHBoxLayout()
        self.cb_alpha = QtWidgets.QCheckBox("Sort channels alphabetically")
        self.cb_alpha.setChecked(True)
        opts_h.addWidget(self.cb_alpha)
        opts_h.addStretch()
        layout.addLayout(opts_h)

        # Generate button
        self.btn_generate = QtWidgets.QPushButton("Generate Sorted Playlist")
        layout.addWidget(self.btn_generate)
