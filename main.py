import sys
import os
from PyQt5 import QtWidgets
from ui.checker_ui import CheckerUI
from ui.sorter_ui  import SorterUI
from controllers.checker_controller import CheckerController
from controllers.sorter_controller  import SorterController
from options import OptionsDialog
from styles import STYLE_SHEET

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker & Playlist Sorter")
        self.resize(1000, 700)

        # Holders for sharing into OptionsDialog
        self.categories       = {}
        self.group_entries    = {}
        self.selected_groups  = []
        self.current_m3u_file = ""

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

        # Options dialog gets updated before each open
        self.options_dialog = OptionsDialog(self.categories,
                                            self.group_entries,
                                            parent=self)

        # Hook up controllers
        self.checker_ctrl = CheckerController(self.checker_ui,
                                              self.options_dialog)
        self.sorter_ctrl  = SorterController(self.sorter_ui)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with three buttons
        bar = QtWidgets.QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #5b2fc9;")
        bar_layout = QtWidgets.QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 0, 0, 0)

        self.btn_iptv     = QtWidgets.QPushButton("IPTV Checker")
        self.btn_playlist = QtWidgets.QPushButton("Playlist Sorter")
        self.btn_options  = QtWidgets.QPushButton("Options")
        for btn in (self.btn_iptv, self.btn_playlist, self.btn_options):
            btn.setCheckable(True)
            btn.setStyleSheet(
                "color:white; background:transparent; font-weight:bold; border:none;"
            )
            bar_layout.addWidget(btn)
        self.btn_iptv.setChecked(True)  # default

        bar_layout.addStretch()
        layout.addWidget(bar)

        # Stacked pages
        self.pages     = QtWidgets.QStackedWidget()
        self.checker_ui= CheckerUI()
        self.sorter_ui = SorterUI()
        self.pages.addWidget(self.checker_ui)
        self.pages.addWidget(self.sorter_ui)
        layout.addWidget(self.pages)

        # Wire button clicks
        self.btn_iptv.clicked    .connect(lambda: self._switch_page(0))
        self.btn_playlist.clicked.connect(lambda: self._switch_page(1))
        self.btn_options.clicked .connect(self._open_options)

    def _switch_page(self, idx):
        # Toggle the check state
        self.btn_iptv.setChecked(idx == 0)
        self.btn_playlist.setChecked(idx == 1)
        self.pages.setCurrentIndex(idx)

    def _open_options(self):
        # Before opening, sync in the latest state from the checker controller
        cc = self.checker_ctrl
        self.options_dialog.categories       = cc.categories
        self.options_dialog.group_urls       = cc.group_entries
        self.options_dialog.selected_groups  = cc.selected_groups
        self.options_dialog.le_m3u.setText(cc.m3u_file)
        self.options_dialog.le_out.setText(cc.output_dir)
        self.options_dialog.sp_workers.setValue(cc.workers)
        self.options_dialog.sp_retries.setValue(cc.retries)
        self.options_dialog.sp_timeout.setValue(cc.timeout)
        self.options_dialog.cb_split.setChecked(cc.split)
        self.options_dialog.cb_update_quality.setChecked(cc.update_quality)
        self.options_dialog.cb_update_fps.setChecked(cc.update_fps)
        self.options_dialog.cb_include_untested.setChecked(cc.include_untested)

        if self.options_dialog.exec_() == QtWidgets.QDialog.Accepted:
            # New settings are picked up by CheckerController on next start_check()
            pass

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
