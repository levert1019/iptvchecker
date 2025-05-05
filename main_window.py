#!/usr/bin/env python3
# main_window.py

import sys
import os
from PyQt5 import QtWidgets, QtCore
from ui_main_window import Ui_MainWindow
from checker import IPTVChecker
from playlist_sorter import PlaylistSorter

class MainWindow(QtWidgets.QMainWindow):
    """
    Main application window for IPTV Checker + Playlist Sorter.
    Routes Start/Pause/Stop buttons to whichever tab is active.
    """
    IPTV_TAB_INDEX   = 0
    SORTER_TAB_INDEX = 1

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Instantiate controllers
        self.checker = IPTVChecker(parent=self)
        self.sorter  = PlaylistSorter()

        # Wire up Start/Pause/Stop buttons to dispatcher methods
        self.ui.btnStart.clicked.connect(self._on_start)
        self.ui.btnPause.clicked.connect(self._on_pause)
        self.ui.btnStop.clicked.connect(self._on_stop)

    def _on_start(self):
        idx = self.ui.tabWidget.currentIndex()
        if idx == self.IPTV_TAB_INDEX:
            self.checker.start()
        elif idx == self.SORTER_TAB_INDEX:
            # Pass in current M3U path & output dir if needed:
            m3u = self.ui.leM3U.text().strip()
            out = self.ui.leOutput.text().strip() or None
            self.sorter.start(m3u, out)

    def _on_pause(self):
        idx = self.ui.tabWidget.currentIndex()
        if idx == self.IPTV_TAB_INDEX:
            self.checker.pause()
        elif idx == self.SORTER_TAB_INDEX:
            self.sorter.pause()

    def _on_stop(self):
        idx = self.ui.tabWidget.currentIndex()
        if idx == self.IPTV_TAB_INDEX:
            self.checker.stop()
        elif idx == self.SORTER_TAB_INDEX:
            self.sorter.stop()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
