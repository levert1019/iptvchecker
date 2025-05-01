# dialogs.py

from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for selecting channel groups, showing Live, Movies, and Series
    categories side by side with a dark theme, enhanced checkbox styling,
    shift-click selection, and context menu options. The list fills the
    full height of the dialog.
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
        # Width fixed; height matches parent or nearly full screen
        width = 900
        if parent:
            height = parent.height()
        else:
            height = QtWidgets.QApplication.primaryScreen().availableGeometry().height() - 100
        self.resize(width, height)

        # Fusion + dark palette
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

        # Style smaller fancy checkboxes with border
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet(f"""
            QListWidget::indicator {{
                width: 12px; height: 12px;
                border: 2px solid {self.TEXT};
                border-radius: 3px;
                background: {self.BG};
            }}
            QListWidget::indicator:checked {{ background: {self.ACCENT}; }}
            QCheckBox::indicator {{
                width: 12px; height: 12px;
                border: 2px solid {self.TEXT};
                border-radius: 3px;
                background: {self.BG};
            }}
            QCheckBox::indicator:checked {{ background: {self.ACCENT}; }}
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
            panel.setStyleSheet(f"border: 2px solid {self.BORDER}; border-radius: 6px;")
            vbox = QtWidgets.QVBoxLayout(panel)
            vbox.setContentsMargins(0, 0, 0, 0)

            # Header
            header = QtWidgets.QLabel(title)
            header.setAlignment(QtCore.Qt.AlignCenter)
            header.setFixedHeight(30)
            header.setStyleSheet(
                f"background-color: {self.ACCENT}; color: {self.TEXT}; font-weight: bold; padding: 4px;"
            )
            vbox.addWidget(header)

            # Toggle-all button
            btn = QtWidgets.QPushButton("Select/Unselect All")
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                f"background-color: {self.ACCENT}; color: {self.TEXT}; border: none; font-size: 12pt;"
            )
            btn.clicked.connect(lambda _, k=key: self._toggle_all(k))
            vbox.addWidget(btn)

            # List widget: fill remaining space
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(self._context_menu)
            lw.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

            for grp in self.categories.get(key, []):
                count = len(self.group_urls.get(grp, []))
                item = QtWidgets.QListWidgetItem(f"{grp} ({count})")
                item.setData(QtCore.Qt.UserRole, grp)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                lw.addItem(item)

            vbox.addWidget(lw, 1)
            setattr(self, f"{key.lower()}_lw", lw)
            cats_layout.addWidget(panel)
            cats_layout.setStretch(cats_layout.count()-1, 1)

        main_layout.addLayout(cats_layout, 1)

        # OK/Cancel
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def _toggle_all(self, category):
        lw = getattr(self, f"{category.lower()}_lw")
        target = QtCore.Qt.Checked if any(
            lw.item(i).checkState() == QtCore.Qt.Unchecked
            for i in range(lw.count())
        ) else QtCore.Qt.Unchecked
        for i in range(lw.count()):
            lw.item(i).setCheckState(target)

    def _context_menu(self, pos):
        lw = self.sender()
        menu = QtWidgets.QMenu(lw)
        act_all = menu.addAction("Check All")
        act_none = menu.addAction("Uncheck All")
        menu.addSeparator()
        act_sel = menu.addAction("Check Selected Groups")
        act_unsel = menu.addAction("Uncheck Selected Groups")
        action = menu.exec_(lw.mapToGlobal(pos))
        if action == act_all:
            for i in range(lw.count()): lw.item(i).setCheckState(QtCore.Qt.Checked)
        elif action == act_none:
            for i in range(lw.count()): lw.item(i).setCheckState(QtCore.Qt.Unchecked)
        elif action == act_sel:
            for item in lw.selectedItems(): item.setCheckState(QtCore.Qt.Checked)
        elif action == act_unsel:
            for item in lw.selectedItems(): item.setCheckState(QtCore.Qt.Unchecked)

    def selected_groups(self) -> list[str]:
        result = []
        for key in ("Live", "Movie", "Series"):
            lw = getattr(self, f"{key.lower()}_lw")
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    result.append(item.data(QtCore.Qt.UserRole))
        return result