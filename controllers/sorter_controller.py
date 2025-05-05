import os
from PyQt5 import QtWidgets
from services.parser import parse_groups
from services.playlist_sorter import sort_entries, write_sorted

class SorterController:
    """
    Encapsulates the Playlist Sorter logic:
      - browsing for an M3U file
      - loading its groups into the UI tree
      - generating and writing the sorted playlist
    """
    def __init__(self, ui):
        self.ui = ui
        self._connect_signals()

    def _connect_signals(self):
        # Wire up the Browse… and Generate buttons
        self.ui.btn_browse.clicked.connect(self.browse)
        self.ui.btn_generate.clicked.connect(self.generate)

    def browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Select M3U to sort",
            filter="*.m3u"
        )
        if not path:
            return

        # Display chosen file
        self.ui.le_sort_m3u.setText(path)

        # Parse groups and populate the tree widget
        groups, _ = parse_groups(path)
        self.ui.tree_groups.clear()
        for grp in groups:
            item = QtWidgets.QTreeWidgetItem([grp])
            self.ui.tree_groups.addTopLevelItem(item)

    def generate(self):
        m3u = self.ui.le_sort_m3u.text().strip()
        if not m3u:
            QtWidgets.QMessageBox.warning(
                None,
                "Missing File",
                "Please select an M3U file first."
            )
            return

        # Gather group order from the tree
        group_order = [
            self.ui.tree_groups.topLevelItem(i).text(0)
            for i in range(self.ui.tree_groups.topLevelItemCount())
        ]

        # Choose sort key (currently only 'name' or 'uid')
        key = "name" if self.ui.cb_alpha.isChecked() else "uid"

        # Perform sorting
        try:
            lines = sort_entries(m3u, group_order, channel_sort_key=key)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                None,
                "Error Sorting Playlist",
                f"An error occurred:\n{e}"
            )
            return

        # Write out the sorted M3U
        out_path = os.path.splitext(m3u)[0] + "_sorted.m3u"
        try:
            write_sorted(lines, out_path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                None,
                "Error Writing File",
                f"Failed to write sorted playlist:\n{e}"
            )
            return

        # Success message
        QtWidgets.QMessageBox.information(
            None,
            "Playlist Sorted",
            f"Sorted playlist written to:\n{out_path}"
        )
