import sys
import os
from PyQt5 import QtWidgets, uic
from output_writer import write_output_files
from parser import parse_groups
from main_window import IPTVChecker

class IPTVCheckerController(QtWidgets.QMainWindow):
    def __init__(self):
        super(IPTVCheckerController, self).__init__()
        # Load the UI file (assumes iptv_checker.ui is in the same directory)
        ui_path = os.path.join(os.path.dirname(__file__), 'iptv_checker.ui')
        uic.loadUi(ui_path, self)

        # Connect UI signals
        self.btn_load_playlist.clicked.connect(self.load_playlist)
        self.btn_run_tests.clicked.connect(self.run_tests)

        # Prepare storage
        self.original_lines = []
        self.extinf_map = {}
        self.status_map = {}
        self.base_name = ''
        self.output_dir = os.getcwd()  # default to current working directory

    def load_playlist(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select M3U File",
            "",
            "M3U Files (*.m3u);;All Files (*)"
        )
        if not file_path:
            return

        # Parse the playlist into original lines and an EXTINF map
        self.original_lines, self.extinf_map = parse_m3u(file_path)
        self.base_name = os.path.splitext(os.path.basename(file_path))[0]
        self.output_dir = os.path.dirname(file_path)
        self.log.emit('info', f"Loaded playlist '{self.base_name}.m3u' with {len(self.extinf_map)} channels.")

    def run_tests(self):
        if not self.extinf_map:
            self.log.emit('warning', "No playlist loaded. Please load an M3U file first.")
            return

        # Run reachability/status tests on all channels
        tester = IPTVTester(self.extinf_map)
        self.status_map = tester.test_all()
        self.log.emit('info', "Channel testing complete.")

        # Determine whether to write output M3U(s)
        if any([
            self.cb_update_quality.isChecked(),
            self.cb_update_fps.isChecked(),
            self.cb_split.isChecked(),
            self.cb_include_untested.isChecked()
        ]):
            output_files = write_output_files(
                original_lines=self.original_lines,
                entry_map=self.extinf_map,
                statuses=self.status_map,
                base_name=self.base_name,
                output_dir=self.output_dir,
                split=self.cb_split.isChecked(),
                update_quality=self.cb_update_quality.isChecked(),
                update_fps=self.cb_update_fps.isChecked(),
                include_untested=self.cb_include_untested.isChecked()
            )
            for path in output_files:
                self.log.emit('info', f"Exported M3U: {path}")
        else:
            self.log.emit('info', "No output options selected; skipping M3U export.")

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = IPTVCheckerController()
    window.show()
    sys.exit(app.exec_())
