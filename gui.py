import sys
from PyQt5 import QtWidgets
from parser import parse_groups
from checker import check_stream
from qt_helpers import GroupSelectionDialog  # we'll create this shortly

class IPTVCheckerWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DonTV IPTV Checker")
        # … copy over your _setup_ui() and _apply_style() methods here …
        # Ensure that when you call parse_groups or check_stream,
        # you import them from parser.py and checker.py respectively.

    # … other methods (_load_file, _on_select_groups, etc.) …

def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    window = IPTVCheckerWindow()
    window.show()
    sys.exit(app.exec_())
