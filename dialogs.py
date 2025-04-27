# dialogs.py
from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    def __init__(self, categories: dict, group_urls: dict, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.group_urls = group_urls

        self.setWindowTitle("Select Groups")
        self.resize(700, 400)

        layout = QtWidgets.QHBoxLayout()
        font   = QtGui.QFont()
        font.setPointSize(10)

        # One column per category
        for cat_name, grp_list in categories.items():
            box = QtWidgets.QGroupBox(cat_name)
            box.setFont(font)
            vbox = QtWidgets.QVBoxLayout()
            lw   = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

            # Add groups in original order, with count
            for grp in grp_list:
                count = len(group_urls.get(grp, []))
                item = QtWidgets.QListWidgetItem(f"{grp} ({count})")
                item.setData(QtCore.Qt.UserRole, grp)
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
        sel = []
        for cat_name in self.categories:
            lw = getattr(self, f"{cat_name.lower()}_lw", None)
            if not lw:
                continue
            for i in range(lw.count()):
                it = lw.item(i)
                if it.checkState() == QtCore.Qt.Checked:
                    sel.append(it.data(QtCore.Qt.UserRole))
        return sel

    def selected_groups(self) -> list[str]:
        return self.selected()
