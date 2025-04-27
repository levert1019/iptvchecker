from PyQt5 import QtWidgets, QtGui, QtCore
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET, DEEP_PURPLE, TEXT_LIGHT, HEADER_FONT
import sys, os, queue, threading
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from dialogs import GroupSelectionDialog
from workers import WorkerThread
from styles import STYLE_SHEET
# …  
class IPTVChecker(QtWidgets.QMainWindow):
    # …
    from workers import WorkerThread

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # … init code …
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        # all the layout code (header, buttons, tables, console)… unchanged

    # callbacks: _on_browse_m3u, _on_select_groups, start_check, pause_check, etc.
    # unchanged except imports and maybe shifting helpers into utils if desired
