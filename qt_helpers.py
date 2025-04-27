from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    def __init__(self, categories: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Groups")
        self.resize(700, 400)

        layout = QtWidgets.QHBoxLayout()
        font = QtGui.QFont()
        font.setPointSize(10)

        # One list widget per category
        for cat_name, groups in categories.items():
            box = QtWidgets.QGroupBox(cat_name)
            box.setFont(font)
            vbox = QtWidgets.QVBoxLayout()
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
            for g in sorted(set(groups)):
                item = QtWidgets.QListWidgetItem(g)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                lw.addItem(item)
            vbox.addWidget(lw)
            box.setLayout(vbox)
            setattr(self, f"{cat_name.lower()}_lw", lw)
            layout.addWidget(box)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(layout)
        main_layout.addWidget(btns)

    def selected(self) -> list[str]:
        """Return list of checked group names."""
        sel: list[str] = []
        for attr in ['live_lw', 'movie_lw', 'series_lw']:
            lw = getattr(self, attr)
            for i in range(lw.count()):
                it = lw.item(i)
                if it.checkState() == QtCore.Qt.Checked:
                    sel.append(it.text())
        return sel