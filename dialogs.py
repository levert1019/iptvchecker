from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for selecting channel groups, showing Live, Movies, and Series
    categories side by side with a dark theme and enhanced styling.
    """
    ACCENT_COLOR = "#9b2cfc"
    BACKGROUND_COLOR = "#222222"
    TEXT_COLOR = "#ffffff"
    LIST_BG_COLOR = "#2e2e2e"
    PANEL_BORDER_COLOR = "#9b2cfc"

    def __init__(self, categories: dict, group_urls: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Groups")
        self.resize(900, 500)

        # Fusion dark palette
        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        dark_palette = QtGui.QPalette()
        dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(self.BACKGROUND_COLOR))
        dark_palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(self.TEXT_COLOR))
        dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(self.LIST_BG_COLOR))
        dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(self.BACKGROUND_COLOR))
        dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(self.TEXT_COLOR))
        dark_palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(self.TEXT_COLOR))
        dark_palette.setColor(QtGui.QPalette.Text, QtGui.QColor(self.TEXT_COLOR))
        dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(self.ACCENT_COLOR))
        dark_palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(self.TEXT_COLOR))
        dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(self.ACCENT_COLOR))
        dark_palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(self.TEXT_COLOR))
        QtWidgets.QApplication.instance().setPalette(dark_palette)

        self.categories = categories
        self.group_urls = group_urls

        main_layout = QtWidgets.QVBoxLayout(self)
        cats_layout = QtWidgets.QHBoxLayout()
        cats_layout.setSpacing(20)

        # Define display names and order
        display_order = [("Live", "Live Channels"), ("Movie", "Movies"), ("Series", "Series")]

        for key, title in display_order:
            panel = QtWidgets.QFrame()
            panel.setFrameShape(QtWidgets.QFrame.Box)
            panel.setStyleSheet(f"QFrame {{ border: 2px solid {self.PANEL_BORDER_COLOR}; border-radius: 6px; }}")
            vbox = QtWidgets.QVBoxLayout(panel)
            vbox.setContentsMargins(0, 0, 0, 0)

            # Header
            header = QtWidgets.QLabel(title)
            header.setAlignment(QtCore.Qt.AlignCenter)
            header.setFixedHeight(30)
            header.setStyleSheet(
                f"QLabel {{ background-color: {self.ACCENT_COLOR}; color: {self.TEXT_COLOR};"
                " font-weight: bold; padding: 4px; }}"
            )
            vbox.addWidget(header)

            # Select/Unselect All button
            btn = QtWidgets.QPushButton("Select/Unselect All")
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {self.ACCENT_COLOR}; color: {self.TEXT_COLOR};"
                " border: none; font-size: 12pt; }}"
            )
            btn.clicked.connect(lambda _, k=key: self._toggle_all(k))
            vbox.addWidget(btn)

            # List widget
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            lw.setStyleSheet(
                f"QListWidget {{ background-color: {self.LIST_BG_COLOR}; color: {self.TEXT_COLOR};"
                " border: none; padding: 4px; }}"
                "QListWidget::item {{ margin: 2px 0; }}"
            )
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(self._context_menu)

            # Populate groups
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
        main_layout.addSpacing(10)

        # Dialog buttons
        btns = QtWidgets.QDialogButtonBox()
        ok_btn = btns.addButton(QtWidgets.QDialogButtonBox.Ok)
        cancel_btn = btns.addButton(QtWidgets.QDialogButtonBox.Cancel)
        ok_btn.setText("OK")
        cancel_btn.setText("Cancel")
        ok_btn.setStyleSheet(f"QPushButton {{ background-color: {self.ACCENT_COLOR}; color: {self.TEXT_COLOR}; border-radius:4px; padding:6px; }}")
        cancel_btn.setStyleSheet(f"QPushButton {{ background-color: {self.ACCENT_COLOR}; color: {self.TEXT_COLOR}; border-radius:4px; padding:6px; }}")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.setCenterButtons(True)
        main_layout.addWidget(btns)

    def _toggle_all(self, category):
        lw = getattr(self, f"{category.lower()}_lw", None)
        if not lw:
            return
        # If any unchecked exist, check all; otherwise uncheck all
        target = QtCore.Qt.Checked if any(lw.item(i).checkState() == QtCore.Qt.Unchecked for i in range(lw.count())) else QtCore.Qt.Unchecked
        for i in range(lw.count()):
            lw.item(i).setCheckState(target)

    def _context_menu(self, pos):
        lw = self.sender()
        menu = QtWidgets.QMenu(lw)
        act_all = menu.addAction("Select All")
        act_none = menu.addAction("Deselect All")
        action = menu.exec_(lw.mapToGlobal(pos))
        if action == act_all:
            for i in range(lw.count()): lw.item(i).setCheckState(QtCore.Qt.Checked)
        elif action == act_none:
            for i in range(lw.count()): lw.item(i).setCheckState(QtCore.Qt.Unchecked)

    def selected_groups(self) -> list[str]:
        result = []
        for key in ["Live", "Movie", "Series"]:
            lw = getattr(self, f"{key.lower()}_lw", None)
            if lw:
                for i in range(lw.count()):
                    item = lw.item(i)
                    if item.checkState() == QtCore.Qt.Checked:
                        result.append(item.data(QtCore.Qt.UserRole))
        return result
