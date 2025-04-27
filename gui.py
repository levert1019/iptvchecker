import sys
from PyQt5 import QtWidgets, QtGui, QtCore
from parser import parse_groups

# Theme colors
DEEP_PURPLE = "#5b2fc9"
DARK_BG     = "#2b2b2b"
MID_BG      = "#3c3f41"
TEXT_LIGHT  = "#e0e0e0"
HEADER_FONT = "Arial"

# Shared dark theme stylesheet
STYLE_SHEET = f"""
QMainWindow, QDialog {{ background: {DARK_BG}; color: {TEXT_LIGHT}; }}
QLabel, QGroupBox::title {{ color: {TEXT_LIGHT}; }}
QLineEdit {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; }}
QListWidget {{ background: {MID_BG}; color: {TEXT_LIGHT}; border: none; padding-right: 20px; }}
QPushButton {{
    background: {DEEP_PURPLE};
    color: white;
    border-radius: 4px;
    padding: 6px;
}}
QPushButton:hover {{ background: #7e52e0; }}
QGroupBox {{
    background: {MID_BG};
    border: 2px solid {DEEP_PURPLE};
    margin-top: 1em;
    padding: 0px;
}}
QScrollArea {{ background: {DARK_BG}; border: none; padding: 0px; margin: 0px; }}
QScrollArea > QWidget {{ background: {DARK_BG}; margin: 0px; padding: 0px; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {MID_BG};
    width: 12px;
    height: 12px;
}}
QScrollBar::handle {{
    background: {DEEP_PURPLE};
    min-height: 20px;
    border-radius: 6px;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
}}
"""

class GroupSelectionDialog(QtWidgets.QDialog):
    def __init__(self, categories: dict, group_urls: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Groups")
        self.resize(900, 600)
        self.setStyleSheet(STYLE_SHEET)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setContentsMargins(0,0,0,0)
        content = QtWidgets.QWidget()
        scroll.setWidget(content)

        grid = QtWidgets.QGridLayout(content)
        grid.setContentsMargins(10,10,10,10)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)

        self.list_widgets = {}
        for col, cat in enumerate(['Live', 'Movie', 'Series']):
            groups = categories.get(cat, [])
            box = QtWidgets.QGroupBox(f"{cat} Channels")
            box_layout = QtWidgets.QVBoxLayout()
            box_layout.setContentsMargins(10,10,10,10)
            box_layout.setSpacing(5)

            # Buttons: Select All & Unselect All
            btn_layout = QtWidgets.QHBoxLayout()
            btn_layout.setContentsMargins(0,0,0,0)
            btn_layout.setSpacing(5)
            btn_select_all = QtWidgets.QPushButton("Select All")
            btn_unselect_all = QtWidgets.QPushButton("Unselect All")
            btn_layout.addWidget(btn_select_all)
            btn_layout.addWidget(btn_unselect_all)
            box_layout.addLayout(btn_layout)

            # List widget for group items
            lw = QtWidgets.QListWidget()
            lw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            lw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(
                lambda pos, lw=lw: self.open_context_menu(lw, pos)
            )

            for g in groups:
                count = len(group_urls.get(g, []))
                item = QtWidgets.QListWidgetItem(f"{g} ({count})")
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                lw.addItem(item)
            box_layout.addWidget(lw)

            # Connect button actions
            btn_select_all.clicked.connect(
                lambda _, lw=lw: self._set_all_check_state(lw, QtCore.Qt.Checked)
            )
            btn_unselect_all.clicked.connect(
                lambda _, lw=lw: self._set_all_check_state(lw, QtCore.Qt.Unchecked)
            )

            box.setLayout(box_layout)
            grid.addWidget(box, 0, col)
            self.list_widgets[cat] = lw

        main_layout.addWidget(scroll)

        # OK / Cancel
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _set_all_check_state(self, lw, state):
        for i in range(lw.count()):
            lw.item(i).setCheckState(state)

    def open_context_menu(self, lw, pos):
        menu = QtWidgets.QMenu()
        action_check   = menu.addAction("Check Selected")
        action_uncheck = menu.addAction("Uncheck Selected")
        chosen = menu.exec_(lw.mapToGlobal(pos))
        if chosen == action_check:
            for item in lw.selectedItems():
                item.setCheckState(QtCore.Qt.Checked)
        elif chosen == action_uncheck:
            for item in lw.selectedItems():
                item.setCheckState(QtCore.Qt.Unchecked)

    def selected_groups(self) -> list[str]:
        selections = []
        for lw in self.list_widgets.values():
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    name = item.text().rsplit(' (', 1)[0]
                    selections.append(name)
        return selections

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(800, 600)
        self.group_urls = {}
        self.categories = {}
        self.selected = []
        self._setup_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _setup_ui(self):
        central = QtWidgets.QWidget()
        layout  = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(10)

        # Header
        header = QtWidgets.QLabel()
        header.setText(
            f'<span style="font-family:{HEADER_FONT}; font-weight:bold; font-size:28pt; '
            f'color:{TEXT_LIGHT};">Don</span>'
            f'<span style="font-family:{HEADER_FONT}; font-weight:bold; font-size:28pt; '
            f'color:{DEEP_PURPLE};">TV</span>'
            f'<span style="font-family:{HEADER_FONT}; font-weight:bold; font-size:16pt; '
            f'color:{TEXT_LIGHT};"> IPTV Checker</span>'
        )
        header.setAlignment(QtCore.Qt.AlignCenter)
        header.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(header)

        # File picker + select
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0,0,0,0)
        top.setSpacing(5)
        self.file_input = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Browse M3U")
        btn_browse.clicked.connect(self._browse_file)
        self.btn_select_groups = QtWidgets.QPushButton("Select Groups")
        self.btn_select_groups.setEnabled(False)
        self.btn_select_groups.clicked.connect(self._open_group_selection)

        top.addWidget(self.file_input)
        top.addWidget(btn_browse)
        top.addWidget(self.btn_select_groups)
        layout.addLayout(top)

        self.setCentralWidget(central)

    def _browse_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U File", "", "M3U Files (*.m3u)"
        )
        if path:
            self.file_input.setText(path)
            groups_dict, cats = parse_groups(path)
            self.group_urls = groups_dict
            self.categories  = cats
            self.btn_select_groups.setEnabled(True)

    def _open_group_selection(self):
        dlg = GroupSelectionDialog(self.categories, self.group_urls, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected = dlg.selected_groups()
            QtWidgets.QMessageBox.information(
                self, "Selected Groups",
                f"You selected {len(self.selected)} groups."
            )

def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    window = IPTVChecker()
    window.show()
    sys.exit(app.exec_())
