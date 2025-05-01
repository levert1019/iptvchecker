# dialogs.py

from PyQt5 import QtWidgets, QtGui, QtCore

class GroupSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for selecting channel groups, showing categories side by side
    with dark theme, fancy checkboxes, shift-click selection, and context menu.
    """
    ACCENT = "#9b2cfc"
    BG     = "#222222"
    TEXT   = "#ffffff"
    BORDER = "#9b2cfc"

    def __init__(self, categories: dict, group_urls: dict, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.group_urls = group_urls
        self.setWindowTitle("Select Groups")
        width = 900
        height = parent.height() if parent else QtWidgets.QApplication.primaryScreen().availableGeometry().height() - 100
        self.resize(width, height)

        # Fusion dark palette
        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(self.BG))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(self.TEXT))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(self.BG))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor(self.ACCENT))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(self.TEXT))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(self.ACCENT))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(self.TEXT))
        QtWidgets.QApplication.instance().setPalette(pal)

        # Checkbox & list indicators
        QtWidgets.QApplication.instance().setStyleSheet(f"""
            QListWidget::indicator {{ width:12px; height:12px; border:2px solid {self.TEXT}; border-radius:3px; background:{self.BG}; }}
            QListWidget::indicator:checked {{ background:{self.ACCENT}; }}
            QCheckBox::indicator {{ width:12px; height:12px; border:2px solid {self.TEXT}; border-radius:3px; background:{self.BG}; }}
            QCheckBox::indicator:checked {{ background:{self.ACCENT}; }}
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        cats_layout = QtWidgets.QHBoxLayout()
        cats_layout.setSpacing(20)

        # Fixed order for common categories, then any others
        preferred = ['Live', 'Movie', 'Series']
        ordered_keys = [k for k in preferred if k in self.categories]
        ordered_keys += [k for k in self.categories if k not in preferred]

        for key in ordered_keys:
            panel = QtWidgets.QFrame()
            panel.setFrameShape(QtWidgets.QFrame.Box)
            panel.setStyleSheet(f"border:2px solid {self.BORDER}; border-radius:6px;")
            vbox = QtWidgets.QVBoxLayout(panel)
            vbox.setContentsMargins(0,0,0,0)

            # Header
            header = QtWidgets.QLabel(key)
            header.setAlignment(QtCore.Qt.AlignCenter)
            header.setFixedHeight(30)
            header.setStyleSheet(f"background-color:{self.ACCENT}; color:{self.TEXT}; font-weight:bold; padding:4px;")
            vbox.addWidget(header)

            # Select/Unselect all
            btn = QtWidgets.QPushButton("Select/Unselect All")
            btn.setFixedHeight(30)
            btn.setStyleSheet(f"background-color:{self.ACCENT}; color:{self.TEXT}; border:none; font-size:12pt;")
            btn.clicked.connect(lambda _, k=key: self._toggle_all(k))
            vbox.addWidget(btn)

            # List
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(self._context_menu)
            lw.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

            for grp in self.categories.get(key, []):
                item = QtWidgets.QListWidgetItem(f"{grp} ({len(self.group_urls.get(grp, []))})")
                item.setData(QtCore.Qt.UserRole, grp)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                lw.addItem(item)

            vbox.addWidget(lw, 1)
            setattr(self, f"{key.lower()}_lw", lw)
            cats_layout.addWidget(panel)
            cats_layout.setStretch(cats_layout.count()-1, 1)

        main_layout.addLayout(cats_layout, 1)

        # OK / Cancel
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def _toggle_all(self, category):
        lw = getattr(self, f"{category.lower()}_lw")
        target = QtCore.Qt.Checked if any(lw.item(i).checkState() == QtCore.Qt.Unchecked for i in range(lw.count())) else QtCore.Qt.Unchecked
        for i in range(lw.count()):
            lw.item(i).setCheckState(target)

    def _context_menu(self, pos):
        lw = self.sender()
        menu = QtWidgets.QMenu(lw)
        menu.addAction("Check All", lambda: [lw.item(i).setCheckState(QtCore.Qt.Checked) for i in range(lw.count())])
        menu.addAction("Uncheck All", lambda: [lw.item(i).setCheckState(QtCore.Qt.Unchecked) for i in range(lw.count())])
        menu.addSeparator()
        menu.addAction("Check Selected", lambda: [item.setCheckState(QtCore.Qt.Checked) for item in lw.selectedItems()])
        menu.addAction("Uncheck Selected", lambda: [item.setCheckState(QtCore.Qt.Unchecked) for item in lw.selectedItems()])
        menu.exec_(lw.mapToGlobal(pos))

    def selected_groups(self) -> list[str]:
        result = []
        for key in ['Live','Movie','Series']:
            if key not in self.categories:
                continue
            lw = getattr(self, f"{key.lower()}_lw")
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    result.append(item.data(QtCore.Qt.UserRole))
        return result
