import sys
import os
import threading
import re
import queue
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET
from utils import QUALITY_LABELS, sup_digits, format_fps, resolution_to_label, clean_name
from ui_main_window import build_ui

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        build_ui(self)
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)
        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []
        self.tasks_q = None
        self.threads = []
        self.results = {}
        self.url_map = {}
        self.extinf_map = {}
        self.status_map = {}
        self.log_records = []
        self.remaining = 0
        self._is_paused = False
        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)



if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
