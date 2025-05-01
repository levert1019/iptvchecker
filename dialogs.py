# dialogs.py

from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for selecting channel groups, showing Live, Movies, and Series
    categories side by side with a dark theme, select/deselect-all
    buttons, and properly styled checkboxes.
    """
    ACCENT = "#9b2cfc"
    BG = "#222222"
    TEXT = "#ffffff"
    LIST_BG = "#2e2e2e"
    BORDER = "#9b2cfc"

    def __init__(self, categories: dict, group_urls: dict, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.group_urls = group_urls
        self.setWindowTitle("Select Groups")
        self.resize(900, 500)

        # Fusion + dark theme + checkbox styling
        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(self.BG))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(self.TEXT))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(self.LIST_BG))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(self.BG))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(self.ACCENT))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(self.TEXT))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(self.ACCENT))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(self.TEXT))
        QtWidgets.QApplication.instance().setPalette(palette)

        # Additional stylesheet for list‐item checkboxes
        self.setStyleSheet(f"""
            QListView::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {self.TEXT};
                background: {self.TEXT};
            }}
            QListView::indicator:checked {{
                background: {self.ACCENT};
            }}
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        cats_layout = QtWidgets.QHBoxLayout()
        cats_layout.setSpacing(20)

        display_order = [("Live", "Live Channels"),
                         ("Movie", "Movies"),
                         ("Series", "Series")]

        for key, title in display_order:
            panel = QtWidgets.QFrame()
            panel.setFrameShape(QtWidgets.QFrame.Box)
            panel.setStyleSheet(f"QFrame {{ border: 2px solid {self.BORDER}; border-radius: 6px; }}")
            vbox = QtWidgets.QVBoxLayout(panel)
            vbox.setContentsMargins(0, 0, 0, 0)

            # Header
            header = QtWidgets.QLabel(title)
            header.setAlignment(QtCore.Qt.AlignCenter)
            header.setFixedHeight(30)
            header.setStyleSheet(
                f"QLabel {{ background-color: {self.ACCENT}; color: {self.TEXT}; "
                "font-weight: bold; padding: 4px; }}"
            )
            vbox.addWidget(header)

            # Toggle-all button
            btn = QtWidgets.QPushButton("Select/Unselect All")
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {self.ACCENT}; color: {self.TEXT}; "
                "border: none; font-size: 12pt; }}"
            )
            btn.clicked.connect(lambda _, k=key: self._toggle_all(k))
            vbox.addWidget(btn)

            # List widget
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(self._context_menu)
            for grp in self.categories.get(key, []):
                count = len(self.group_urls.get(grp, []))
                item = QtWidgets.QListWidgetItem(f"{grp} ({count})")
                item.setData(QtCore.Qt.UserRole, grp)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                lw.addItem(item)
            vbox.addWidget(lw)

            setattr(self, f"{key.lower()}_lw", lw)
            cats_layout.addWidget(panel)

        main_layout.addLayout(cats_layout)
        main_layout.addStretch()

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def _toggle_all(self, category):
        lw = getattr(self, f"{category.lower()}_lw")
        # check if any unchecked → then check all, else uncheck all
        target = QtCore.Qt.Checked if any(lw.item(i).checkState() == QtCore.Qt.Unchecked 
                                          for i in range(lw.count())) else QtCore.Qt.Unchecked
        for i in range(lw.count()):
            lw.item(i).setCheckState(target)

    def _context_menu(self, pos):
        lw = self.sender()
        menu = QtWidgets.QMenu(lw)
        act_all = menu.addAction("Select All")
        act_none = menu.addAction("Deselect All")
        action = menu.exec_(lw.mapToGlobal(pos))
        if action == act_all:
            for i in range(lw.count()):
                lw.item(i).setCheckState(QtCore.Qt.Checked)
        elif action == act_none:
            for i in range(lw.count()):
                lw.item(i).setCheckState(QtCore.Qt.Unchecked)

    def selected_groups(self) -> list[str]:
        result = []
        for key in ("Live", "Movie", "Series"):
            lw = getattr(self, f"{key.lower()}_lw")
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    result.append(item.data(QtCore.Qt.UserRole))
        return result
