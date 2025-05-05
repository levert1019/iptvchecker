# options.py

import os
import re
import json
from typing import Dict, List
from PyQt5 import QtWidgets, QtCore

# Regex to extract the group-title attribute
_GROUP_RE = re.compile(r'group-title="([^"]*)"', re.IGNORECASE)

def _parse_categories(m3u_path: str) -> Dict[str, Dict[str, int]]:
    """
    Read the M3U and bucket each entry into exactly one of:
      • "Live Channels" if neither 'movie' nor 'series' appears in the URL
      • "Movies" if 'movie' appears in the URL
      • "Series" if 'series' appears in the URL

    Returns a dict mapping category → { group_title: count, … }
    in the order groups first appear in the file.
    """
    cats = {
        "Live Channels": {},
        "Movies": {},
        "Series": {},
    }
    with open(m3u_path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF'):
            continue
        m = _GROUP_RE.search(line)
        group = m.group(1) if m else "Other"
        url = lines[i+1] if i+1 < len(lines) else ""
        lower = url.lower()
        if 'series' in lower:
            bucket = cats["Series"]
        elif 'movie' in lower:
            bucket = cats["Movies"]
        else:
            bucket = cats["Live Channels"]
        if group not in bucket:
            bucket[group] = 0
        bucket[group] += 1
    return cats


class GroupSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for selecting which groups to include, categorized into
    Live Channels | Movies | Series.
    """
    def __init__(self, m3u_file: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Groups")
        self.resize(900, 500)
        self.cats = _parse_categories(m3u_file)
        self.selected_groups: List[str] = []
        self._checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self._build_ui()

    def _build_ui(self):
        main_v = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(container)
        h.setContentsMargins(5, 5, 5, 5)
        h.setSpacing(10)

        for cat_title in ("Live Channels", "Movies", "Series"):
            box = QtWidgets.QGroupBox(cat_title)
            box.setStyleSheet("""
                QGroupBox {
                  border: 2px solid #5b2fc9;
                  border-radius: 5px;
                  margin-top: 6px;
                }
                QGroupBox::title {
                  background: #5b2fc9;
                  color: white;
                  subcontrol-origin: margin;
                  left: 10px;
                  padding: 0 3px;
                }
            """)
            v = QtWidgets.QVBoxLayout(box)
            btn_all = QtWidgets.QPushButton("Select/Unselect All")
            btn_all.setStyleSheet("background-color:#5b2fc9; color:white;")
            btn_all.clicked.connect(lambda _, c=cat_title: self._toggle_all(c))
            v.addWidget(btn_all)

            col_scroll = QtWidgets.QScrollArea()
            col_scroll.setWidgetResizable(True)
            inner = QtWidgets.QWidget()
            iv = QtWidgets.QVBoxLayout(inner)
            iv.setContentsMargins(0, 0, 0, 0)
            iv.setSpacing(2)

            for group, count in self.cats[cat_title].items():
                cb = QtWidgets.QCheckBox(f"{group} ({count} channels)")
                self._checkboxes[f"{cat_title}|{group}"] = cb
                iv.addWidget(cb)
            iv.addStretch()
            col_scroll.setWidget(inner)
            v.addWidget(col_scroll, 1)
            h.addWidget(box)

        scroll.setWidget(container)
        main_v.addWidget(scroll, 1)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        main_v.addWidget(bb)

    def _toggle_all(self, category: str):
        any_off = any(
            not cb.isChecked()
            for k, cb in self._checkboxes.items()
            if k.startswith(category + "|")
        )
        for k, cb in self._checkboxes.items():
            if k.startswith(category + "|"):
                cb.setChecked(any_off)

    def _on_accept(self):
        self.selected_groups = [
            k.split("|", 1)[1]
            for k, cb in self._checkboxes.items()
            if cb.isChecked()
        ]
        self.accept()


class OptionsDialog(QtWidgets.QDialog):
    """
    Main Options dialog:
      - choose M3U file
      - launch GroupSelectionDialog
      - choose output folder
      - set IPTV Checker settings
      - set Playlist Sorter settings (TMDB API Key, workers, add year)
    """
    CONFIG_FILE = "config.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(800, 520)
        self.selected_groups: List[str] = []
        # placeholder for playlist sorter settings
        self.le_tmdbApiKey: QtWidgets.QLineEdit
        self.sp_playlist_workers: QtWidgets.QSpinBox
        self.cb_add_year: QtWidgets.QCheckBox
        self._build_ui()
        self._load_playlist_sorter_settings()

    def _build_ui(self):
        main_v = QtWidgets.QVBoxLayout(self)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(15)

        # ── Main Options ─────────────────────────────────────────
        gb1 = QtWidgets.QGroupBox("Main Options")
        gb1.setStyleSheet("""
            QGroupBox { border:2px solid #5b2fc9; border-radius:5px; margin-top:6px; }
            QGroupBox::title { background:#5b2fc9; color:white; subcontrol-origin:margin; left:10px; padding:0 3px; }
        """)
        grid = QtWidgets.QGridLayout(gb1)
        grid.setVerticalSpacing(8); grid.setHorizontalSpacing(10)

        grid.addWidget(QtWidgets.QLabel("M3U File:"), 0, 0)
        self.le_m3u = QtWidgets.QLineEdit()
        b1 = QtWidgets.QPushButton("Browse…"); b1.clicked.connect(self._browse_m3u)
        h1 = QtWidgets.QHBoxLayout(); h1.addWidget(self.le_m3u); h1.addWidget(b1)
        grid.addLayout(h1, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Groups:"), 1, 0)
        self.btn_groups = QtWidgets.QPushButton("Select Groups…")
        self.btn_groups.clicked.connect(self._open_group_dialog)
        grid.addWidget(self.btn_groups, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Output Directory:"), 2, 0)
        self.le_out = QtWidgets.QLineEdit(os.getcwd())
        b2 = QtWidgets.QPushButton("Browse…"); b2.clicked.connect(self._browse_out)
        h2 = QtWidgets.QHBoxLayout(); h2.addWidget(self.le_out); h2.addWidget(b2)
        grid.addLayout(h2, 2, 1)

        main_v.addWidget(gb1, 0)

        # ── IPTV Checker Settings ───────────────────────────────
        gb2 = QtWidgets.QGroupBox("IPTV Checker Settings")
        gb2.setStyleSheet(gb1.styleSheet())
        form2 = QtWidgets.QFormLayout(gb2)
        form2.setLabelAlignment(QtCore.Qt.AlignRight)
        form2.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        form2.setHorizontalSpacing(20); form2.setVerticalSpacing(8)

        self.sp_workers = QtWidgets.QSpinBox(); self.sp_workers.setRange(1, 100)
        self.sp_retries = QtWidgets.QSpinBox(); self.sp_retries.setRange(0, 10)
        self.sp_timeout = QtWidgets.QSpinBox(); self.sp_timeout.setRange(1, 300)
        form2.addRow("Workers:", self.sp_workers)
        form2.addRow("Retries:", self.sp_retries)
        form2.addRow("Timeout (s):", self.sp_timeout)

        self.cb_split = QtWidgets.QCheckBox("Split output into separate files")
        self.cb_update_quality = QtWidgets.QCheckBox("Update resolution label")
        self.cb_update_fps = QtWidgets.QCheckBox("Update FPS label")
        self.cb_include_untested = QtWidgets.QCheckBox("Include untested entries")
        form2.addRow(self.cb_split)
        form2.addRow(self.cb_update_quality)
        form2.addRow(self.cb_update_fps)
        form2.addRow(self.cb_include_untested)

        main_v.addWidget(gb2, 1)

        # ── Playlist Sorter Settings ────────────────────────────
        gb3 = QtWidgets.QGroupBox("Playlist Sorter Settings")
        gb3.setStyleSheet(gb1.styleSheet())
        form3 = QtWidgets.QFormLayout(gb3)
        form3.setLabelAlignment(QtCore.Qt.AlignRight)
        form3.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        form3.setHorizontalSpacing(20); form3.setVerticalSpacing(8)

        # TMDB API Key + Save
        self.le_tmdbApiKey = QtWidgets.QLineEdit()
        form3.addRow("TMDB API Key:", self.le_tmdbApiKey)
        self.btn_save_tmdb = QtWidgets.QPushButton("Save")
        self.btn_save_tmdb.clicked.connect(self._save_playlist_sorter_settings)
        form3.addRow(self.btn_save_tmdb)

        # Number of workers for playlist sorter
        self.sp_playlist_workers = QtWidgets.QSpinBox()
        self.sp_playlist_workers.setRange(1, 64)
        form3.addRow("Amount of Workers:", self.sp_playlist_workers)

        # Add Year to Name checkbox
        self.cb_add_year = QtWidgets.QCheckBox("Add Year to Name")
        form3.addRow(self.cb_add_year)

        main_v.addWidget(gb3, 2)

        # ── OK / Cancel ──────────────────────────────────────────
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        main_v.addWidget(bb)

    def _browse_m3u(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select M3U file", filter="*.m3u"
        )
        if path:
            self.le_m3u.setText(path)

    def _browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output directory", options=QtWidgets.QFileDialog.ShowDirsOnly
        )
        if path:
            self.le_out.setText(path)

    def _open_group_dialog(self):
        m3u = self.le_m3u.text().strip()
        if not m3u:
            QtWidgets.QMessageBox.warning(self, "No M3U", "Please select an M3U file first.")
            return
        dlg = GroupSelectionDialog(m3u, parent=self)
        dlg.selected_groups = list(self.selected_groups)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups

    def _load_playlist_sorter_settings(self):
        """
        Load TMDB key, playlist workers, and Add Year flag from CONFIG_FILE
        and populate the controls.
        """
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.le_tmdbApiKey.setText(cfg.get("tmdb_api_key", ""))
            self.sp_playlist_workers.setValue(cfg.get("playlist_workers", 4))
            self.cb_add_year.setChecked(cfg.get("add_year_to_name", False))

    def _save_playlist_sorter_settings(self):
        """
        Save the playlist sorter settings to CONFIG_FILE.
        Creates or updates the JSON file as needed.
        """
        cfg = {}
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                try:
                    cfg = json.load(f)
                except json.JSONDecodeError:
                    cfg = {}
        cfg["tmdb_api_key"]      = self.le_tmdbApiKey.text().strip()
        cfg["playlist_workers"]  = self.sp_playlist_workers.value()
        cfg["add_year_to_name"]  = self.cb_add_year.isChecked()
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        QtWidgets.QMessageBox.information(self, "Saved", "Playlist Sorter settings saved.")

    def get_options(self) -> dict:
        """
        Return all options as a dict (including main, checker, and sorter settings).
        """
        return {
            "m3u_file": self.le_m3u.text().strip(),
            "workers": self.sp_workers.value(),
            "retries": self.sp_retries.value(),
            "timeout": self.sp_timeout.value(),
            "split": self.cb_split.isChecked(),
            "update_quality": self.cb_update_quality.isChecked(),
            "update_fps": self.cb_update_fps.isChecked(),
            "include_untested": self.cb_include_untested.isChecked(),
            "output_dir": self.le_out.text().strip(),
            "selected_groups": self.selected_groups,
            "tmdb_api_key": self.le_tmdbApiKey.text().strip(),
            "playlist_workers": self.sp_playlist_workers.value(),
            "add_year_to_name": self.cb_add_year.isChecked(),
        }
