# controllers/sorter_controller.py

import os
import threading
from PyQt5 import QtWidgets, QtCore
from services.playlist_sorter import PlaylistSorter

class SorterController(QtCore.QObject):
    """
    Controller for the Playlist Sorter tab.
    Manages start, pause, resume, and stop actions, and routes log messages into the GUI console.
    Optimized to append new logs incrementally to avoid UI lag.
    """
    log_signal = QtCore.pyqtSignal(str, str)  # (level, message)

    def __init__(self, ui, options_dialog, main_window):
        super().__init__(main_window)
        self.ui = ui
        self.options = options_dialog
        self.main_window = main_window
        self.sorter = PlaylistSorter()
        self.m3u_file = ""
        self.output_dir = os.getcwd()
        self._logbuf = []

        # Connect sorter logs to handler
        self.log_signal.connect(self._on_log)
        # Filters trigger full refresh only when toggled
        for cb in (self.ui.cb_show_working, self.ui.cb_show_info, self.ui.cb_show_error):
            cb.stateChanged.connect(self._refresh_console)

        # Clear console initially
        self.ui.te_console.clear()

    def start(self):
        opts = self.options.get_options()
        m3u = opts["m3u_file"]
        if not m3u or not os.path.isfile(m3u):
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Missing or Invalid M3U",
                "Please select a valid M3U file in Options."
            )
            return

        # Persist paths
        self.m3u_file = m3u
        self.output_dir = opts["output_dir"] or os.getcwd()

        # Apply sorter-specific options
        self.sorter.api_key             = opts["tmdb_api_key"]
        self.sorter.max_workers         = opts["playlist_workers"]
        self.sorter.add_year            = opts["add_year_to_name"]
        self.sorter.update_name         = opts["update_name"]
        self.sorter.update_banner       = opts["update_banner"]
        self.sorter.export_only_sorted  = opts["export_just_sorted"]

        # Clear any previous stop/pause
        if hasattr(self.sorter, "_stop_event"):
            self.sorter._stop_event.clear()
        if hasattr(self.sorter, "_pause_event"):
            self.sorter._pause_event.clear()

        # Redirect logs to GUI
        self.sorter.logger = lambda lvl, msg: self.log_signal.emit(lvl, msg)

        # Clear console history
        self._logbuf.clear()
        self.ui.te_console.clear()

        # Launch sorter in background
        thread = threading.Thread(
            target=self.sorter.start,
            args=(m3u, self.output_dir, opts["selected_groups"]),
            daemon=True
        )
        thread.start()

    def pause(self):
        """Pause sorting."""
        if hasattr(self.sorter, "pause"):
            self.sorter.pause()

    def resume(self):
        """Resume sorting."""
        if hasattr(self.sorter, "resume"):
            self.sorter.resume()

    def stop(self):
        """Stop the sorter cleanly."""
        if hasattr(self.sorter, "stop"):
            self.sorter.stop()

    def _on_log(self, level, msg):
        """Handle a new log message: buffer it and append incrementally."""
        # Store in buffer for future filter-refresh
        self._logbuf.append((level, msg))

        # Only append the new message to the console (no full clear)
        colors = {"working": "green", "info": "orange", "error": "red"}
        cb = getattr(self.ui, f"cb_show_{level}", None)
        if cb and cb.isChecked():
            self.ui.te_console.append(f'<span style="color:{colors[level]}">{msg}</span>')

    def _refresh_console(self):
        """Re-render full console based on current filter states (on toggle)."""
        self.ui.te_console.clear()
        colors = {"working": "green", "info": "orange", "error": "red"}
        for lvl, msg in self._logbuf:
            cb = getattr(self.ui, f"cb_show_{lvl}", None)
            if cb and cb.isChecked():
                self.ui.te_console.append(f'<span style="color:{colors[lvl]}">{msg}</span>')
