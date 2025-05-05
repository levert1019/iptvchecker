# main.py

import sys
from PyQt5 import QtWidgets, QtCore
from ui.checker_ui import CheckerUI
from ui.sorter_ui import SorterUI
from controllers.checker_controller import CheckerController
from options import OptionsDialog
from styles import STYLE_SHEET

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker & Playlist Sorter")
        self.resize(1000, 700)

        # central widget & layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # instantiate the page UIs
        self.checker_ui = CheckerUI()
        self.sorter_ui  = SorterUI()

        # ────────── TOP NAV BAR ──────────
        nav_bar = QtWidgets.QFrame()
        nav_bar.setObjectName("nav_bar")
        nav_bar.setFixedHeight(40)
        nav_layout = QtWidgets.QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(5)

        # IPTV Checker button
        self.btn_iptv = QtWidgets.QPushButton("IPTV Checker")
        self.btn_iptv.setCheckable(True)
        self.btn_iptv.setChecked(True)
        nav_layout.addWidget(self.btn_iptv)

        # bigger gap before Playlist Sorter
        nav_layout.addSpacing(30)

        # Playlist Sorter button
        self.btn_playlist = QtWidgets.QPushButton("Playlist Sorter")
        self.btn_playlist.setCheckable(True)
        nav_layout.addWidget(self.btn_playlist)

        # stretch so the control buttons/options go to the right
        nav_layout.addStretch()

        # Start/Pause/Stop grouped tightly
        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.setSpacing(4)
        btns_layout.addWidget(self.checker_ui.btn_start)
        btns_layout.addWidget(self.checker_ui.btn_pause)
        btns_layout.addWidget(self.checker_ui.btn_stop)
        nav_layout.addLayout(btns_layout)

        # Options button at the far right
        self.btn_options = QtWidgets.QPushButton("Options")
        nav_layout.addWidget(self.btn_options)

        main_layout.addWidget(nav_bar)

        # ────────── PAGES ──────────
        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self.checker_ui)
        self.pages.addWidget(self.sorter_ui)
        main_layout.addWidget(self.pages)

        # ────────── STATUS BAR ──────────
        self.setStatusBar(QtWidgets.QStatusBar())

        # apply global stylesheet
        self.setStyleSheet(STYLE_SHEET)

        # shared Options dialog
        self.options_dialog = OptionsDialog(parent=self)

        # controllers
        self.checker_ctrl = CheckerController(
            ui=self.checker_ui,
            options_dialog=self.options_dialog,
            main_window=self
        )

        # hook up nav buttons
        self.btn_iptv.clicked    .connect(lambda: self._switch_page(0))
        self.btn_playlist.clicked.connect(lambda: self._switch_page(1))
        self.btn_options.clicked .connect(self._open_options)

    def _switch_page(self, idx: int):
        self.btn_iptv.setChecked(idx == 0)
        self.btn_playlist.setChecked(idx == 1)
        self.pages.setCurrentIndex(idx)

    def _open_options(self):
        cc = self.checker_ctrl
        # sync current settings
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
            # new settings take effect on next start_check()
            pass

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
