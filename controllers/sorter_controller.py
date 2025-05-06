# controllers/sorter_controller.py

import os
from PyQt5 import QtWidgets
from services.playlist_sorter import PlaylistSorter

class SorterController:
    """
    Controller for the Playlist Sorter tab.
    Manages start, pause, and stop actions, pulling settings from OptionsDialog.
    """

    def __init__(self, ui, options_dialog, main_window):
        self.ui = ui
        self.options = options_dialog
        self.main_window = main_window
        self.sorter = PlaylistSorter()

    def start(self):
        """
        Begin sorting: read M3U path and output directory from the shared Options dialog,
        then invoke the PlaylistSorter.
        """
        m3u_file = self.options.le_m3u.text().strip()
        if not m3u_file or not os.path.isfile(m3u_file):
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Missing or Invalid M3U",
                "Please select a valid M3U file in Options."
            )
            return

        output_dir = self.options.le_out.text().strip() or None
        self.sorter.start(m3u_file, output_dir)

    def pause(self):
        """Pause or resume the sorter."""
        self.sorter.pause()

    def stop(self):
        """Stop the sorter."""
        self.sorter.stop()
