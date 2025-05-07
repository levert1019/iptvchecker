#!/usr/bin/env python3
import sys
from PyQt5 import QtWidgets, QtCore

from ui.checker_ui import CheckerUI
from ui.sorter_ui import SorterUI
from controllers.checker_controller import CheckerController
from controllers.sorter_controller import SorterController
from options import OptionsDialog
from styles import STYLE_SHEET

class MainWindow(QtWidgets.QMainWindow):
    """
    Main application window for IPTV Checker & Playlist Sorter.
    The Start/Pause/Stop controls dispatch to the active tab's controller.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker & Playlist Sorter")
        self.resize(1000, 700)

        # ───── Central widget & layout ─────
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ───── Instantiate UIs ─────
        self.checker_ui = CheckerUI()
        self.sorter_ui  = SorterUI()

        # ───── Shared Options dialog ─────
        self.options_dialog = OptionsDialog(parent=self)

        # ───── Instantiate controllers ─────
        self.checker_ctrl = CheckerController(
            ui=self.checker_ui,
            options_dialog=self.options_dialog,
            main_window=self
        )
        self.sorter_ctrl = SorterController(
            ui=self.sorter_ui,
            options_dialog=self.options_dialog,
            main_window=self
        )

        # ───── TOP NAV BAR ─────
        nav_bar = QtWidgets.QFrame()
        nav_bar.setObjectName("nav_bar")
        nav_bar.setFixedHeight(40)
        nav_layout = QtWidgets.QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(5)

        # — Script switch buttons —
        self.btn_iptv     = QtWidgets.QPushButton("IPTV Checker")
        self.btn_iptv.setCheckable(True)
        self.btn_iptv.setChecked(True)
        nav_layout.addWidget(self.btn_iptv)

        nav_layout.addSpacing(30)

        self.btn_playlist = QtWidgets.QPushButton("Playlist Sorter")
        self.btn_playlist.setCheckable(True)
        nav_layout.addWidget(self.btn_playlist)

        nav_layout.addStretch()

        # — Start / Pause / Stop —
        self.btn_start = QtWidgets.QPushButton("Start")
        self.btn_pause = QtWidgets.QPushButton("Pause")
        self.btn_stop  = QtWidgets.QPushButton("Stop")
        # Pause/Stop disabled until Start is pressed
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

        ctrl_layout = QtWidgets.QHBoxLayout()
        ctrl_layout.setSpacing(4)
        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_pause)
        ctrl_layout.addWidget(self.btn_stop)
        nav_layout.addLayout(ctrl_layout)

        # — Options button —
        self.btn_options = QtWidgets.QPushButton("Options")
        nav_layout.addWidget(self.btn_options)

        main_layout.addWidget(nav_bar)

        # ───── PAGES ─────
        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self.checker_ui)
        self.pages.addWidget(self.sorter_ui)
        main_layout.addWidget(self.pages)

        # ───── STATUS BAR ─────
        self.setStatusBar(QtWidgets.QStatusBar())

        # ───── Apply stylesheet ─────
        self.setStyleSheet(STYLE_SHEET)

        # ───── Signal wiring ─────
        self.btn_iptv.clicked.connect(lambda: self._switch_page(0))
        self.btn_playlist.clicked.connect(lambda: self._switch_page(1))
        self.btn_options.clicked.connect(self._open_options)

        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_stop.clicked.connect(self._on_stop)

    def _switch_page(self, idx: int):
        """
        Switch to tab idx (0=IPTV, 1=Sorter) and reset controls.
        """
        self.pages.setCurrentIndex(idx)
        self.btn_iptv.setChecked(idx == 0)
        self.btn_playlist.setChecked(idx == 1)
        self._reset_controls()

    def _reset_controls(self):
        """
        Reset Start/Pause/Stop button states when switching tabs.
        """
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self.btn_stop.setEnabled(False)

    def _on_start(self):
        """
        Dispatch Start to the active controller.
        """
        idx = self.pages.currentIndex()
        if idx == 0:
            # IPTV page → call CheckerController.start_check()
            self.checker_ctrl.start_check()
        else:
            # Sorter page → call SorterController.start()
            self.sorter_ctrl.start()

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def _on_pause(self):
        """
        Dispatch Pause/Resume to the active controller,
        and toggle the button label.
        """
        idx = self.pages.currentIndex()
        if idx == 0:
            # IPTV page → call CheckerController._toggle_pause()
            self.checker_ctrl._toggle_pause()
        else:
            # Sorter page → call SorterController.pause()
            self.sorter_ctrl.pause()

        # Toggle label
        if self.btn_pause.text() == "Pause":
            self.btn_pause.setText("Resume")
        else:
            self.btn_pause.setText("Pause")

    def _on_stop(self):
        """
        Dispatch Stop to the active controller and reset controls.
        """
        idx = self.pages.currentIndex()
        if idx == 0:
            # IPTV page → call CheckerController.stop_check()
            self.checker_ctrl.stop_check()
        else:
            # Sorter page → call SorterController.stop()
            self.sorter_ctrl.stop()

        self._reset_controls()

    def _open_options(self):
        """
        Open the Options dialog, pre-populating fields from
        whichever controller is active.
        """
        idx = self.pages.currentIndex()
        ctrl = self.checker_ctrl if idx == 0 else self.sorter_ctrl

        # Populate dialog fields (example for checker; extend for sorter)
        self.options_dialog.le_m3u.setText(ctrl.m3u_file)
        self.options_dialog.le_out.setText(ctrl.output_dir)
        if hasattr(ctrl, "workers"):
            self.options_dialog.sp_workers.setValue(ctrl.workers)
        # ... (populate other fields as needed) ...

        if self.options_dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Any new settings will apply on next Start press
            pass

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
