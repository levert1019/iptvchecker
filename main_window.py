import sys
import os
import re
import queue
import threading
from PyQt5 import QtWidgets, QtCore
from parser import parse_groups
from workers import WorkerThread
from dialogs import GroupSelectionDialog
from styles import STYLE_SHEET
from utils import QUALITY_LABELS, sup_digits, format_fps, resolution_to_label, clean_name
from ui_main_window import build_ui

class IPTVChecker(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        build_ui(self)
        self.setWindowTitle("DonTV IPTV Checker")
        self.resize(1000, 700)
        self.group_urls = {}
        self.categories = {}
        self.selected_groups = []
        self.tasks_q = None
        self.threads = []
        self.results = {}
        self.url_map = {}
        self.extinf_map = {}
        self.status_map = {}
        self.log_records = []
        self.remaining = 0
        self._is_paused = False
        self.setStyleSheet(STYLE_SHEET)

    def _on_browse_m3u(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select M3U File", "", "M3U Files (*.m3u)")
        if fn:
            self.le_m3u.setText(fn)
            self.group_urls, self.categories = parse_groups(fn)
            self.selected_groups = []
            self.btn_select.setEnabled(True)

    def _on_select_groups(self):
        dlg = GroupSelectionDialog(self.categories, self.group_urls, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.selected_groups = dlg.selected_groups()

    def _on_browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            self.le_out.setText(d)

    def start_check(self):
        if not self.selected_groups:
            QtWidgets.QMessageBox.warning(self, "No Groups", "Please select at least one group.")
            return
        self.results.clear(); self.url_map.clear(); self.extinf_map.clear(); self.status_map.clear(); self.log_records.clear()
        for tbl in (self.tbl_working, self.tbl_black_screen, self.tbl_non_working): tbl.setRowCount(0)
        self.tasks_q = queue.Queue()
        for grp in self.selected_groups:
            for ent in self.group_urls.get(grp, []):
                name, url, ext = ent['name'], ent['url'], ent['extinf']
                self.tasks_q.put((name, url))
                self.url_map[name] = url; self.extinf_map[name] = ext
        self.threads = []; self.remaining = self.sp_workers.value()
        for _ in range(self.remaining):
            t = WorkerThread(self.tasks_q, self.sp_retries.value(), self.sp_timeout.value())
            t.result.connect(self._on_result); t.log.connect(self._on_log); t.finished.connect(self._thread_done)
            t.start(); self.threads.append(t)
        self.btn_start.setEnabled(False); self.btn_pause.setEnabled(True); self.btn_stop.setEnabled(True)
        self.status.showMessage("Checking started", 3000)

    def _thread_done(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self._finish_up()

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        for t in self.threads: t.pause() if self._is_paused else t.resume()
        self.btn_pause.setText("Resume" if self._is_paused else "Pause")
        state = "Paused" if self._is_paused else "Resumed"
        QtWidgets.QMessageBox.information(self, f"Checking {state}", f"Checking {state.lower()}…")
        self.status.showMessage(state, 3000)

    def stop_check(self):
        for t in self.threads: t.stop()
        QtWidgets.QMessageBox.information(self, "Checking Stopped", "Checking stopped.")
        self.status.showMessage("Stopped", 3000)
        threading.Thread(target=self._finish_up, daemon=True).start()

    def _on_result(self, name, status, res, fps):
        self.results[name] = (res, fps)
        key = 'working' if status == 'UP' else 'black_screen' if status == 'BLACK_SCREEN' else 'non_working'
        self.status_map[name] = key
        tbl = getattr(self, f"tbl_{key}")
        row = tbl.rowCount(); tbl.insertRow(row)
        formatted = name
        formatted = re.sub(r"\b(sd|hd|fhd|uhd)\b", lambda m: QUALITY_LABELS[m.group(1).lower()], formatted, flags=re.IGNORECASE)
        formatted = re.sub(r"\d+(?:/\d+)?bps?", lambda m: format_fps(m.group(0)), formatted, flags=re.IGNORECASE)
        if self.cb_update_quality.isChecked() or self.cb_update_fps.isChecked():
            base = clean_name(formatted)
            parts = []
            if self.cb_update_quality.isChecked(): parts.append(resolution_to_label(res))
            if self.cb_update_fps.isChecked(): parts.append(format_fps(fps))
            formatted = f"{base} {' '.join(parts)}".strip()
        m = re.search(r"(\d+(?:\.\d+)?)", fps or "")
        num = m.group(1) if m else ''
        if num.endswith('.0'): num = num[:-2]
        tbl.setItem(row, 0, QtWidgets.QTableWidgetItem(formatted))
        tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(res))
        tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(num or '–'))

    def _on_log(self, level, msg):
        self.log_records.append((level, msg))
        self._refresh_console()

    def _refresh_console(self):
        show = {
            'working': self.cb_show_working.isChecked(),
            'info': self.cb_show_info.isChecked(),
            'error': self.cb_show_error.isChecked()
        }
        cmap = {'working': '#00ff00', 'info': '#ffa500', 'error': '#ff0000'}
        self.te_console.clear()
        for lvl, raw in self.log_records:
            if not show.get(lvl): continue
            parts = raw.split('[', 1)
            prefix = parts[0].strip()
            prefix = re.sub(r"\b(sd|hd|fhd|uhd)\b", lambda m: QUALITY_LABELS[m.group(1).lower()], prefix, flags=re.IGNORECASE)
            prefix = re.sub(r"\d+(?:/\d+)?bps?", lambda m: format_fps(m.group(0)), prefix, flags=re.IGNORECASE)
            disp = prefix
            if len(parts) > 1:
                inner = parts[1].rstrip(']')
                rstr, fpsp = inner.split(',', 1)
                if self.cb_update_quality.isChecked() or self.cb_update_fps.isChecked():
                    cn = clean_name(prefix)
                    lbl_parts = []
                    if self.cb_update_quality.isChecked(): lbl_parts.append(resolution_to_label(rstr.strip()))
                    if self.cb_update_fps.isChecked(): lbl_parts.append(format_fps(fpsp))
                    disp = f"{cn} {' '.join(lbl_parts)}".strip()
                else:
                    fs = format_fps(fpsp)
                    disp = f"{prefix} [{rstr.strip()}, {fs}]"
            self.te_console.append(f'<span style="color:{cmap[lvl]}">{disp}</span>')

    def _finish_up(self):
        outd = self.le_out.text() or os.getcwd()
        os.makedirs(outd, exist_ok=True)
        base = os.path.splitext(os.path.basename(self.le_m3u.text()))[0]
        combined = os.path.join(outd, f"{base}.m3u")
        with open(combined, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for name in self.results:
                res, fps = self.results[name]
                ext = self.extinf_map.get(name, '')
                if (self.cb_update_quality.isChecked() or self.cb_update_fps.isChecked()) and ext:
                    base_nm = clean_name(name)
                    parts = []
                    if self.cb_update_quality.isChecked(): parts.append(resolution_to_label(res))
                    if self.cb_update_fps.isChecked(): parts.append(format_fps(fps))
                    new_nm = f"{base_nm} {' '.join(parts)}".strip()
                    ext = re.sub(r'tvg-name="[^"]*"', f'tvg-name="{new_nm}"', ext)
                    ext = re.sub(r",.*$", f",{new_nm}", ext)
                f.write(ext + "\n")
                url = self.url_map.get(name, '')
                if url: f.write(url + "\n")
            if self.cb_include_untested.isChecked():
                for grp_entries in self.group_urls.values():
                    for ent in grp_entries:
                        nm = ent['name']
                        if nm not in self.results:
                            f.write(ent['extinf'] + "\n")
                            f.write(ent['url'] + "\n")
        if self.cb_split.isChecked():
            for key, suffix in [('working', '_working'), ('black_screen', '_blackscreen'), ('non_working', '_nonworking')]:
                path = os.path.join(outd, f"{base}{suffix}.m3u")
                with open(path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for name, status in self.status_map.items():
                        if status == key:
                            ext = self.extinf_map.get(name, '')
                            if (self.cb_update_quality.isChecked() or self.cb_update_fps.isChecked()) and ext:
                                base_nm = clean_name(name)
                                parts = []
                                if self.cb_update_quality.isChecked(): parts.append(resolution_to_label(self.results[name][0]))
                                if self.cb_update_fps.isChecked(): parts.append(format_fps(self.results[name][1]))
                                new_nm = f"{base_nm} {' '.join(parts)}".strip()
                                ext = re.sub(r'tvg-name="[^"]*"', f'tvg-name="{new_nm}"', ext)
                                ext = re.sub(r",.*$", f",{new_nm}", ext)
                            f.write(ext + "\n")
                            url = self.url_map.get(name, '')
                            if url: f.write(url + "\n")
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.status.showMessage("All tasks complete", 5000)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = IPTVChecker()
    win.show()
    sys.exit(app.exec_())
