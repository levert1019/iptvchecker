# main.py
from PyQt5.QtWidgets import QApplication
from main_window import IPTVChecker

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
