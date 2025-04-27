# workers.py
import threading, queue
from PyQt5 import QtCore
from checker import check_stream

class WorkerThread(QtCore.QThread):
    result = QtCore.pyqtSignal(str, str, str, str, str)
    log    = QtCore.pyqtSignal(str, str)
    # … rest of your WorkerThread code, unchanged …
