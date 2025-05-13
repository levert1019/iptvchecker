# controllers/sorter_controller.py

import os
import threading
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui
from config import SortConfig
from services.parser import parse_groups
from services.playlist_sorter import PlaylistSorter

class SorterController(QtCore.QObject):
    log_signal = QtCore.pyqtSignal(str, str)  # (level, message)

    def __init__(self, ui, options_dialog, main_window):
        super().__init__(main_window)
        self.ui = ui
        self.options = options_dialog
        self.main_window = main_window
        self.sorter = None
        self._logbuf = []

        # connect log signal and filters
        self.log_signal.connect(self._on_log)
        self.ui.cb_show_working.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_info.stateChanged.connect(self._refresh_console)
        self.ui.cb_show_error.stateChanged.connect(self._refresh_console)
        self.ui.te_console.clear()

    def start(self):
        opts = self.options.get_options()
        m3u = opts.get('m3u_file')
        if not m3u or not os.path.isfile(m3u):
            QtWidgets.QMessageBox.warning(
                self.main_window,
                'Missing or Invalid M3U',
                'Please select a valid M3U file in Options.'
            )
            return

        # determine which groups
        selected = opts.get('selected_groups', [])
        if not selected:
            all_groups, _ = parse_groups(m3u)
            selected = list(all_groups.keys())
            self.main_window.statusBar().showMessage(
                f'No groups selected—using all {len(selected)}', 3000
            )
        else:
            self.main_window.statusBar().showMessage(
                f'Sorting {len(selected)} selected group(s)', 3000
            )

        # build configuration
        cfg = SortConfig(
            m3u_file=Path(m3u),
            output_dir=Path(opts.get('output_dir') or os.getcwd()),
            selected_groups=selected,
            tmdb_api_key=opts.get('tmdb_api_key',''),
            max_workers=opts.get('playlist_workers',4),
            add_year=opts.get('add_year_to_name',False),
            update_name=opts.get('update_name',False),
            update_banner=opts.get('update_banner',False),
            export_only_sorted=opts.get('export_just_sorted',False),
            genre_map=SortConfig.load_genre_map(Path(opts.get('genre_map'))) if opts.get('genre_map') else {}
        )

        # logger emits to GUI
        def logger(level: str, msg: str):
            self.log_signal.emit(level, msg)

        self.sorter = PlaylistSorter(cfg, logger)

        # clear console buffer and view
        self._logbuf.clear()
        self.ui.te_console.clear()

        # run sorter in background
        thread = threading.Thread(target=self.sorter.start, daemon=True)
        thread.start()

    def _on_log(self, level: str, msg: str):
        # buffer
        self._logbuf.append((level, msg))
        # decide display
        show = False
        if level == 'found':
            show = True
        elif level == 'info' and self.ui.cb_show_info.isChecked():
            show = True
        elif level == 'error' and self.ui.cb_show_error.isChecked():
            show = True
        elif level == 'working' and self.ui.cb_show_working.isChecked():
            show = True

        if show:
            color = {
                'found': 'green',
                'info': 'orange',
                'error': 'red',
                'working': 'black'
            }.get(level, 'black')
            self.ui.te_console.setTextColor(QtGui.QColor(color))
            self.ui.te_console.append(msg)

    def _refresh_console(self):
        self.ui.te_console.clear()
        for level, msg in self._logbuf:
            show = False
            if level == 'found':
                show = True
            elif level == 'info' and self.ui.cb_show_info.isChecked():
                show = True
            elif level == 'error' and self.ui.cb_show_error.isChecked():
                show = True
            elif level == 'working' and self.ui.cb_show_working.isChecked():
                show = True
            if show:
                color = {
                    'found': 'green',
                    'info': 'orange',
                    'error': 'red',
                    'working': 'black'
                }.get(level, 'black')
                self.ui.te_console.setTextColor(QtGui.QColor(color))
                self.ui.te_console.append(msg)

    def pause(self):
        if self.sorter:
            self.sorter.pause()

    def resume(self):
        if self.sorter:
            self.sorter.resume()

    def stop(self):
        if self.sorter:
            self.sorter.stop()
