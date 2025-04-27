# dialogs.py
from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    def __init__(self, categories, group_urls, parent=None):
        """
        Dialog to let the user pick which channel-groups to check.

        Parameters:
        - categories : dict[str, list[str]]      Mapping category-name → list of group-names, in original M3U order
        - group_urls : OrderedDict[str, list[(name, url)]]  Full mapping of group-names to (channel name, url)
        - parent     : Qt parent widget
        """
        super().__init__(parent)
        # store for later use in selected()
        self.categories = categories
        self.group_urls = group_urls

        self.setWindowTitle("Select Groups")
        self.resize(700, 400)

        layout = QtWidgets.QHBoxLayout()
        font   = QtGui.QFont()
        font.setPointSize(10)

        # one list per category, preserving order
        for cat_name, grp_list in categories.items():
            box = QtWidgets.QGroupBox(cat_name)
            box.setFont(font)
            vbox = QtWidgets.QVBoxLayout()
            lw   = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

            for grp in grp_list:
                count = len(group_urls.get(grp, []))
                display = f"{grp} ({count})"
                item = QtWidgets.QListWidgetItem(display)
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
        """Return raw group-names for all checked items, in display order."""
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
        """Alias for backward compatibility."""
        return self.selected()
