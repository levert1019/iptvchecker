# main.py

import sys
from PyQt5 import QtWidgets
from ui.checker_ui import CheckerUI
from ui.sorter_ui import SorterUI
from controllers.checker_controller import CheckerController
from controllers.sorter_controller import SorterController
from options import OptionsDialog
from styles import STYLE_SHEET

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker & Playlist Sorter")
        self.resize(1000, 700)

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

        # Single Options dialog instance
        self.options_dialog = OptionsDialog(parent=self)

        # Pass MainWindow into the controller for statusBar()
        self.checker_ctrl = CheckerController(
            ui=self.checker_ui,
            options_dialog=self.options_dialog,
            main_window=self
        )
        self.sorter_ctrl  = SorterController(self.sorter_ui)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        # Top bar
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #5b2fc9;")
        bl = QtWidgets.QHBoxLayout(bar)
        bl.setContentsMargins(10,0,0,0)

        self.btn_iptv     = QtWidgets.QPushButton("IPTV Checker")
        self.btn_iptv.setCheckable(True)
        self.btn_iptv.setChecked(True)
        self.btn_iptv.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        bl.addWidget(self.btn_iptv)

        self.btn_playlist = QtWidgets.QPushButton("Playlist Sorter")
        self.btn_playlist.setCheckable(True)
        self.btn_playlist.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        bl.addWidget(self.btn_playlist)

        self.btn_options  = QtWidgets.QPushButton("Options")
        self.btn_options.setStyleSheet("color:white; background:transparent; font-weight:bold; border:none;")
        bl.addWidget(self.btn_options)

        bl.addStretch()
        layout.addWidget(bar)

        # Pages
        self.pages      = QtWidgets.QStackedWidget()
        self.checker_ui = CheckerUI()
        self.sorter_ui  = SorterUI()
        self.pages.addWidget(self.checker_ui)
        self.pages.addWidget(self.sorter_ui)
        layout.addWidget(self.pages)

        # Status bar
        self.setStatusBar(QtWidgets.QStatusBar())

        # Hookups
        self.btn_iptv.clicked.connect(lambda: self._switch_page(0))
        self.btn_playlist.clicked.connect(lambda: self._switch_page(1))
        self.btn_options.clicked.connect(self._open_options)

    def _switch_page(self, idx):
        self.btn_iptv.setChecked(idx == 0)
        self.btn_playlist.setChecked(idx == 1)
        self.pages.setCurrentIndex(idx)

    def _open_options(self):
        # Sync every field before showing
        cc = self.checker_ctrl
        self.options_dialog.le_m3u.setText(cc.m3u_file)
        self.options_dialog.le_out.setText(cc.output_dir)
        self.options_dialog.sp_workers.setValue(cc.workers)
        self.options_dialog.sp_retries.setValue(cc.retries)
        self.options_dialog.sp_timeout.setValue(cc.timeout)
        self.options_dialog.cb_split.setChecked(cc.split)
        self.options_dialog.cb_update_quality.setChecked(cc.update_quality)
        self.options_dialog.cb_update_fps.setChecked(cc.update_fps)
        self.options_dialog.cb_include_untested.setChecked(cc.include_untested)
        self.options_dialog.selected_groups = list(cc.selected_groups)

        if self.options_dialog.exec_() == QtWidgets.QDialog.Accepted:
            # New settings will be re‐read by CheckerController.start_check()
            pass

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
