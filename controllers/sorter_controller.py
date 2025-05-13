# controllers/sorter_controller.py

import os
import threading
from PyQt5 import QtWidgets, QtCore
from services.parser import parse_groups
from services.playlist_sorter import PlaylistSorter

class SorterController(QtCore.QObject):
    """
    Controller for the Playlist Sorter tab.
    Manages start, pause, resume, and stop actions,
    routes log messages into the GUI console, and
    applies a 'all-groups' fallback if you haven't picked any.
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

        # Wire GUI console
        self.log_signal.connect(self._on_log)
        for cb in (self.ui.cb_show_working, self.ui.cb_show_info, self.ui.cb_show_error):
            cb.stateChanged.connect(self._refresh_console)
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

        # Persist for Options reload
        self.m3u_file = m3u
        self.output_dir = opts["output_dir"] or os.getcwd()

        # Determine which groups to process; fallback to all if none picked
        selected = opts["selected_groups"]
        if not selected:
            all_groups, _ = parse_groups(m3u)
            selected = list(all_groups.keys())
            self.main_window.statusBar().showMessage(
                f"No groups selected—falling back to all {len(selected)} groups", 3000
            )
        else:
            self.main_window.statusBar().showMessage(
                f"Sorting {len(selected)} selected group(s)", 3000
            )

        # Apply sorter settings
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

        # Redirect logs to the GUI
        self.sorter.logger = lambda lvl, msg: self.log_signal.emit(lvl, msg)

        # Clear the console buffer and view
        self._logbuf.clear()
        self.ui.te_console.clear()

        # Launch in background so the UI stays responsive
        thread = threading.Thread(
            target=self.sorter.start,
            args=(m3u, self.output_dir, selected),
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
        """Append a new log message to the buffer and the console."""
        self._logbuf.append((level, msg))
        # Append only the newest line to avoid redrawing everything
        colors = {"working": "green", "info": "orange", "error": "red"}
        cb = getattr(self.ui, f"cb_show_{level}", None)
        if cb and cb.isChecked():
            self.ui.te_console.append(f'<span style="color:{colors[level]}">{msg}</span>')

    def _refresh_console(self):
        """Re-render the entire console on filter toggles."""
        self.ui.te_console.clear()
        colors = {"working": "green", "info": "orange", "error": "red"}
        for lvl, m in self._logbuf:
            cb = getattr(self.ui, f"cb_show_{lvl}", None)
            if cb and cb.isChecked():
                self.ui.te_console.append(f'<span style="color:{colors[lvl]}">{m}</span>')
