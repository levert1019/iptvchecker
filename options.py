# options.py

import os
import re
import json
from typing import Dict, List
from PyQt5 import QtWidgets, QtCore

# Regex to extract the group-title attribute
_GROUP_RE = re.compile(r'group-title="([^\"]*)"', re.IGNORECASE)

def _parse_categories(m3u_path: str) -> Dict[str, Dict[str, int]]:
    """
    Read the M3U and bucket entries into Live Channels, Movies, or Series.
    Returns a dict mapping category → { group_title: count, … }.
    """
    cats = {"Live Channels": {}, "Movies": {}, "Series": {}}
    with open(m3u_path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF'):
            continue
        m = _GROUP_RE.search(line)
        group = m.group(1) if m else "Other"
        url = lines[i+1] if i+1 < len(lines) else ''
        lower = url.lower()
        if 'series' in lower:
            bucket = cats['Series']
        elif 'movie' in lower:
            bucket = cats['Movies']
        else:
            bucket = cats['Live Channels']
        bucket.setdefault(group, 0)
        bucket[group] += 1
    return cats

class GroupSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for selecting groups from an M3U playlist.
    """
    def __init__(self, m3u_file: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select Groups')
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
        h.setContentsMargins(5,5,5,5)
        h.setSpacing(10)

        box_style = '''
            QGroupBox { border:2px solid #5b2fc9; border-radius:5px; margin-top:6px; }
            QGroupBox::title { background:#5b2fc9; color:white; subcontrol-origin:margin; left:10px; padding:0 3px; }
        '''

        for cat in ('Live Channels','Movies','Series'):
            gb = QtWidgets.QGroupBox(cat)
            gb.setStyleSheet(box_style)
            v = QtWidgets.QVBoxLayout(gb)
            btn = QtWidgets.QPushButton('Select/Unselect All')
            btn.setStyleSheet('background-color:#5b2fc9; color:white;')
            btn.clicked.connect(lambda _, c=cat: self._toggle_all(c))
            v.addWidget(btn)
            col_scroll = QtWidgets.QScrollArea()
            col_scroll.setWidgetResizable(True)
            inner = QtWidgets.QWidget()
            iv = QtWidgets.QVBoxLayout(inner)
            iv.setContentsMargins(0,0,0,0)
            iv.setSpacing(2)
            for grp, cnt in self.cats[cat].items():
                cb = QtWidgets.QCheckBox(f"{grp} ({cnt} channels)")
                self._checkboxes[f"{cat}|{grp}"] = cb
                iv.addWidget(cb)
            iv.addStretch()
            col_scroll.setWidget(inner)
            v.addWidget(col_scroll,1)
            h.addWidget(gb)

        scroll.setWidget(container)
        main_v.addWidget(scroll,1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        main_v.addWidget(bb)

    def _toggle_all(self, category: str):
        any_off = any(not cb.isChecked() for k,cb in self._checkboxes.items() if k.startswith(category+'|'))
        for k,cb in self._checkboxes.items():
            if k.startswith(category+'|'):
                cb.setChecked(any_off)

    def _on_accept(self):
        self.selected_groups = [k.split('|',1)[1] for k,cb in self._checkboxes.items() if cb.isChecked()]
        self.accept()

class OptionsDialog(QtWidgets.QDialog):
    """
    Dialog for all application options, loaded/saved from config.json.
    """
    CONFIG_FILE = 'config.json'
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Options')
        self.resize(800,520)
        self.selected_groups: List[str] = []
        self._build_ui()
        self._load_all_settings()

    def _build_ui(self):
        main_v = QtWidgets.QVBoxLayout(self)
        main_v.setContentsMargins(10,10,10,10)
        main_v.setSpacing(15)

        # Styles
        box_style = '''
            QGroupBox { border:2px solid #5b2fc9; border-radius:5px; margin-top:6px; }
            QGroupBox::title { background:#5b2fc9; color:white; subcontrol-origin:margin; left:10px; padding:0 3px; }
        '''

        # Main Options
        gb1 = QtWidgets.QGroupBox('Main Options')
        gb1.setStyleSheet(box_style)
        grid = QtWidgets.QGridLayout(gb1)
        grid.setVerticalSpacing(8); grid.setHorizontalSpacing(10)
        grid.addWidget(QtWidgets.QLabel('M3U File:'),0,0)
        self.le_m3u = QtWidgets.QLineEdit()
        b1 = QtWidgets.QPushButton('Browse…'); b1.clicked.connect(self._browse_m3u)
        h1=QtWidgets.QHBoxLayout(); h1.addWidget(self.le_m3u); h1.addWidget(b1)
        grid.addLayout(h1,0,1)
        grid.addWidget(QtWidgets.QLabel('Groups:'),1,0)
        self.btn_groups=QtWidgets.QPushButton('Select Groups…'); self.btn_groups.clicked.connect(self._open_group_dialog)
        grid.addWidget(self.btn_groups,1,1)
        grid.addWidget(QtWidgets.QLabel('Output Dir:'),2,0)
        self.le_out=QtWidgets.QLineEdit(os.getcwd())
        b2=QtWidgets.QPushButton('Browse…'); b2.clicked.connect(self._browse_out)
        h2=QtWidgets.QHBoxLayout(); h2.addWidget(self.le_out); h2.addWidget(b2)
        grid.addLayout(h2,2,1)
        main_v.addWidget(gb1)

        # IPTV Checker
        gb2 = QtWidgets.QGroupBox('IPTV Checker Settings')
        gb2.setStyleSheet(box_style)
        form2=QtWidgets.QFormLayout(gb2)
        self.sp_workers=QtWidgets.QSpinBox(); self.sp_workers.setRange(1,100)
        self.sp_retries=QtWidgets.QSpinBox(); self.sp_retries.setRange(0,10)
        self.sp_timeout=QtWidgets.QSpinBox(); self.sp_timeout.setRange(1,300)
        form2.addRow('Workers:',self.sp_workers)
        form2.addRow('Retries:',self.sp_retries)
        form2.addRow('Timeout (s):',self.sp_timeout)
        self.cb_split=QtWidgets.QCheckBox('Split output')
        self.cb_update_quality=QtWidgets.QCheckBox('Update quality')
        self.cb_update_fps=QtWidgets.QCheckBox('Update FPS')
        self.cb_include_untested=QtWidgets.QCheckBox('Include untested')
        form2.addRow(self.cb_split)
        form2.addRow(self.cb_update_quality)
        form2.addRow(self.cb_update_fps)
        form2.addRow(self.cb_include_untested)
        main_v.addWidget(gb2)

        # Playlist Sorter
        gb3 = QtWidgets.QGroupBox('Playlist Sorter Settings')
        gb3.setStyleSheet(box_style)
        form3=QtWidgets.QFormLayout(gb3)
        self.le_tmdbApiKey=QtWidgets.QLineEdit()
        form3.addRow('TMDB API Key:',self.le_tmdbApiKey)
        self.sp_playlist_workers=QtWidgets.QSpinBox(); self.sp_playlist_workers.setRange(1,64)
        form3.addRow('Workers:',self.sp_playlist_workers)
        self.cb_add_year=QtWidgets.QCheckBox('Add Year')
        form3.addRow(self.cb_add_year)
        self.cb_update_banner=QtWidgets.QCheckBox('Update Banner')
        form3.addRow(self.cb_update_banner)
        self.cb_update_name=QtWidgets.QCheckBox('Update Name')
        form3.addRow(self.cb_update_name)
        self.cb_export_only_sorted=QtWidgets.QCheckBox('Export Just Sorted')
        form3.addRow(self.cb_export_only_sorted)
        main_v.addWidget(gb3)

        # Buttons
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok |
            QtWidgets.QDialogButtonBox.Save |
            QtWidgets.QDialogButtonBox.Cancel
        )
        btn_save = bb.button(QtWidgets.QDialogButtonBox.Save)
        btn_save.setText('Save All')
        bb.accepted.connect(self.accept)
        btn_save.clicked.connect(self._save_all_settings)
        bb.rejected.connect(self.reject)
        main_v.addWidget(bb)

    def _browse_m3u(self):
        p,_=QtWidgets.QFileDialog.getOpenFileName(self,'Select M3U','',filter='*.m3u')
        if p: self.le_m3u.setText(p)
    def _browse_out(self):
        p=QtWidgets.QFileDialog.getExistingDirectory(self,'Select Dir',options=QtWidgets.QFileDialog.ShowDirsOnly)
        if p: self.le_out.setText(p)
    def _open_group_dialog(self):
        m3u=self.le_m3u.text().strip()
        if not m3u:
            QtWidgets.QMessageBox.warning(self,'No M3U','Select an M3U file first.')
            return
        dlg=GroupSelectionDialog(m3u,self)
        dlg.selected_groups=self.selected_groups
        for key,cb in dlg._checkboxes.items():
            grp=key.split('|',1)[1]
            cb.setChecked(grp in self.selected_groups)
        if dlg.exec_()==QtWidgets.QDialog.Accepted:
            self.selected_groups=dlg.selected_groups
    def _load_all_settings(self):
        cfg={}
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE,'r',encoding='utf-8') as f: cfg=json.load(f)
            except: cfg={}
        self.le_m3u.setText(cfg.get('m3u_file',''))
        self.le_out.setText(cfg.get('output_dir',os.getcwd()))
        self.selected_groups=cfg.get('selected_groups',[])
        self.sp_workers.setValue(cfg.get('workers',5))
        self.sp_retries.setValue(cfg.get('retries',2))
        self.sp_timeout.setValue(cfg.get('timeout',10))
        self.cb_split.setChecked(cfg.get('split',False))
        self.cb_update_quality.setChecked(cfg.get('update_quality',False))
        self.cb_update_fps.setChecked(cfg.get('update_fps',False))
        self.cb_include_untested.setChecked(cfg.get('include_untested',False))
        self.le_tmdbApiKey.setText(cfg.get('tmdb_api_key',''))
        self.sp_playlist_workers.setValue(cfg.get('playlist_workers',4))
        self.cb_add_year.setChecked(cfg.get('add_year_to_name',False))
        self.cb_update_banner.setChecked(cfg.get('update_banner',False))
        self.cb_update_name.setChecked(cfg.get('update_name',False))
        self.cb_export_only_sorted.setChecked(cfg.get('export_just_sorted',False))
    def _save_all_settings(self):
        cfg={
            'm3u_file':self.le_m3u.text().strip(),
            'output_dir':self.le_out.text().strip(),
            'selected_groups':self.selected_groups,
            'workers':self.sp_workers.value(),
            'retries':self.sp_retries.value(),
            'timeout':self.sp_timeout.value(),
            'split':self.cb_split.isChecked(),
            'update_quality':self.cb_update_quality.isChecked(),
            'update_fps':self.cb_update_fps.isChecked(),
            'include_untested':self.cb_include_untested.isChecked(),
            'tmdb_api_key':self.le_tmdbApiKey.text().strip(),
            'playlist_workers':self.sp_playlist_workers.value(),
            'add_year_to_name':self.cb_add_year.isChecked(),
            'update_banner':self.cb_update_banner.isChecked(),
            'update_name':self.cb_update_name.isChecked(),
            'export_just_sorted':self.cb_export_only_sorted.isChecked(),
        }
        with open(self.CONFIG_FILE,'w',encoding='utf-8') as f:
            json.dump(cfg,f,indent=2)
        QtWidgets.QMessageBox.information(self,'Saved','All settings saved.')
    def get_options(self):
        return {
            'm3u_file':self.le_m3u.text().strip(),
            'workers':self.sp_workers.value(),
            'retries':self.sp_retries.value(),
            'timeout':self.sp_timeout.value(),
            'split':self.cb_split.isChecked(),
            'update_quality':self.cb_update_quality.isChecked(),
            'update_fps':self.cb_update_fps.isChecked(),
            'include_untested':self.cb_include_untested.isChecked(),
            'output_dir':self.le_out.text().strip(),
            'selected_groups':self.selected_groups,
            'tmdb_api_key':self.le_tmdbApiKey.text().strip(),
            'playlist_workers':self.sp_playlist_workers.value(),
            'add_year_to_name':self.cb_add_year.isChecked(),
            'update_banner':self.cb_update_banner.isChecked(),
            'update_name':self.cb_update_name.isChecked(),
            'export_just_sorted':self.cb_export_only_sorted.isChecked(),
        }
