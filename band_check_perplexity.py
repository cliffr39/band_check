import re
import sys
import json
import os
import csv
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QTextEdit, QPushButton, QMessageBox,
    QHBoxLayout, QSplitter, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QDialog, QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QGroupBox, QFileDialog, QAbstractItemView # Import QAbstractItemView for selection modes
)
from PyQt6.QtGui import QColor, QTextCharFormat, QFont
from PyQt6.QtCore import Qt, QSize # Import QSize for fixed size hints

def get_downloads_folder():
    """Return the path to the user's Downloads folder cross-platform, including PyInstaller support."""
    if sys.platform == 'win32':
        try:
            import winreg
            sub_key = r'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders'
            downloads_guid = '{374DE290-123F-4565-9164-39C4925E467B}'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                location = winreg.QueryValueEx(key, downloads_guid)[0]
            if os.path.isdir(location):
                return location
        except Exception:
            pass
        userprofile = os.getenv('USERPROFILE')
        if userprofile:
            path = os.path.join(userprofile, 'Downloads')
            if os.path.isdir(path):
                return path
        path = os.path.join(os.path.expanduser('~'), 'Downloads')
        return path
    else:
        # For macOS and Linux, try XDG first (for localization), else fallback
        try:
            import subprocess
            folder = subprocess.run(
                ["xdg-user-dir", "DOWNLOAD"],
                capture_output=True, text=True
            ).stdout.strip("\n")
            if folder and os.path.isdir(folder):
                return folder
        except Exception:
            pass
        path = os.path.join(os.path.expanduser('~'), 'Downloads')
        return path

DOWNLOADS_FOLDER = get_downloads_folder()
HISTORY_FILE = os.path.join(DOWNLOADS_FOLDER, 'band_checker_history.json') # This will save to Downloads

# START: Corrected parse_phone_bands from band_check.py
def parse_phone_bands(text):
    """
    Parses the input text to extract 4G/LTE and 5G band numbers.
    This version is more robust in handling various formats of band listings
    by using section-aware parsing and stricter regex for LTE bands.
    """
    lte_bands = set()
    nr_bands = set() # 5G New Radio bands

    # --- 5G Band Extraction ---
    # Look for 'n' followed by digits, separated by slashes or commas, or just spaces.
    # This regex now correctly captures all numbers after 'n' until a non-digit/slash/comma/space character.
    # It finds sequences like n1/2/3, n77, n260, etc.
    nr_matches = re.findall(r'n(\d+(?:[/\s,]\d+)*)', text, re.IGNORECASE)
    for match_group in nr_matches:
        # Split the captured group by non-digit characters to get individual band numbers
        individual_bands = re.findall(r'\d+', match_group)
        for band_str in individual_bands:
            try:
                nr_bands.add(int(band_str))
            except ValueError:
                pass

    # --- 4G/LTE Band Extraction ---
    lines = text.split('\n')
    for line in lines:
        line_stripped = line.strip()
        # Check for keywords indicating an LTE line, or if it contains a 'B' followed by digits (e.g., B2).
        # This broadens the scope for LTE detection without relying solely on section headers.
        if re.search(r'\b(4G|LTE|TD-LTE|FDD)\b', line_stripped, re.IGNORECASE) or re.search(r'\bB\d+', line_stripped, re.IGNORECASE):
            # Remove any frequency annotations in parentheses like "(1900)" before extracting bands.
            clean_line = re.sub(r'\s*\([^)]*\)', '', line_stripped)
            # Find all patterns that look like LTE band numbers.
            # This regex captures:
            # - Digits optionally preceded by 'B' (e.g., B2, B41)
            # - Digits that might have an 'A' or 'B' suffix (e.g., 28A will capture '28')
            # The '\b' ensures whole word matching.
            potential_lte_parts = re.findall(r'\bB?(\d+)(?:[abAB])?\b', clean_line, re.IGNORECASE)
            for part in potential_lte_parts:
                try:
                    band_num = int(part)
                    # Simplified filtering: Add band if it's within a typical LTE band range (1 to 100).
                    # LTE and 5G can share band numbers (e.g., n41 is also B41). The context of the line (4G/LTE)
                    # or the presence of 'B' suggests it's an LTE band here.
                    if 1 <= band_num <= 100: # Common LTE bands are typically <= 71, but 100 is a safe upper bound.
                        lte_bands.add(band_num)
                except ValueError:
                    pass

    return sorted(list(lte_bands)), sorted(list(nr_bands))
# END: Corrected parse_phone_bands

def compare_phone_to_carrier(phone_lte_bands, phone_nr_bands, carrier_data):
    results = {}
    for carrier_name, bands_info in carrier_data.items():
        carrier_lte = set(bands_info['4G/LTE'])
        carrier_nr = set(bands_info['5G'])
        carrier_core_lte = set(bands_info['Core LTE'])
        supported_lte = phone_lte_bands.intersection(carrier_lte)
        supported_nr = phone_nr_bands.intersection(carrier_nr)
        missing_lte = carrier_lte - phone_lte_bands
        missing_nr = carrier_nr - phone_nr_bands
        missing_core_lte = carrier_core_lte.intersection(missing_lte)
        results[carrier_name] = {
            'supported_lte': sorted(list(supported_lte)),
            'supported_nr': sorted(list(supported_nr)),
            'missing_lte': sorted(list(missing_lte)),
            'missing_nr': sorted(list(missing_nr)),
            'missing_core_lte': sorted(list(missing_core_lte))
        }
    return results

def calculate_compatibility_score(carrier_results):
    score = 0
    score += len(carrier_results['supported_lte']) * 2.0
    score += len(carrier_results['supported_nr']) * 1.0
    score -= len(carrier_results['missing_core_lte']) * 2.0
    return max(0, score)

class ComparisonDialog(QDialog):
    def __init__(self, comparison_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device Comparison Analysis")
        self.setMinimumSize(1000, 600)
        self.comparison_data = comparison_data
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        title = QLabel("Multi-Device Carrier Compatibility Comparison")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #333;")
        layout.addWidget(title)
        self.table = QTableWidget()
        self.populate_table()
        layout.addWidget(self.table)
        button_layout = QHBoxLayout()
        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_to_csv)
        button_layout.addWidget(export_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def populate_table(self):
        total_rows = 0
        for entry in self.comparison_data:
            total_rows += len(entry['results'])
        self.table.setRowCount(total_rows)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Device", "Carrier", "Compatibility Score",
            "Supported LTE", "Supported 5G", "Missing Core LTE", "Status"
        ])
        row = 0
        for entry in self.comparison_data:
            for carrier, results in entry['results'].items():
                self.table.setItem(row, 0, QTableWidgetItem(entry['model']))
                self.table.setItem(row, 1, QTableWidgetItem(carrier))
                score = calculate_compatibility_score(results)
                score_item = QTableWidgetItem(f"{score:.1f}")
                if score >= 8:
                    score_item.setBackground(QColor(200, 255, 200))
                elif score >= 4:
                    score_item.setBackground(QColor(255, 255, 200))
                else:
                    score_item.setBackground(QColor(255, 200, 200))
                self.table.setItem(row, 2, score_item)
                self.table.setItem(row, 3, QTableWidgetItem(str(results['supported_lte'])))
                self.table.setItem(row, 4, QTableWidgetItem(str(results['supported_nr'])))
                missing_core_item = QTableWidgetItem(str(results['missing_core_lte']))
                if results['missing_core_lte']:
                    missing_core_item.setBackground(QColor(255, 200, 200))
                else:
                    missing_core_item.setBackground(QColor(200, 255, 200))
                self.table.setItem(row, 5, missing_core_item)
                if not results['missing_core_lte']:
                    status = "Excellent"
                    status_color = QColor(200, 255, 200)
                elif len(results['missing_core_lte']) <= 1:
                    status = "Good"
                    status_color = QColor(255, 255, 200)
                else:
                    status = "Limited"
                    status_color = QColor(255, 200, 200)
                status_item = QTableWidgetItem(status)
                status_item.setBackground(status_color)
                self.table.setItem(row, 6, status_item)
                row += 1
        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def export_to_csv(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Comparison", "device_comparison.csv", "CSV Files (*.csv)")
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    headers = []
                    for col in range(self.table.columnCount()):
                        headers.append(self.table.horizontalHeaderItem(col).text())
                    writer.writerow(headers)
                    for row in range(self.table.rowCount()):
                        row_data = []
                        for col in range(self.table.columnCount()):
                            item = self.table.item(row, col)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)
                QMessageBox.information(self, "Export Successful", f"Comparison exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export: {str(e)}")

class BandCheckerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cell Phone Band Compatibility Checker - Enhanced")
        self.initial_left_panel_width = 820
        self.initial_height = 700
        self.history_panel_width = 300
        total_initial_width = self.initial_left_panel_width + 20
        self.setGeometry(100, 100, total_initial_width, self.initial_height)
        self.setMinimumSize(total_initial_width, self.initial_height)
        self.setMaximumWidth(total_initial_width)
        self.setStyleSheet("""
            QMainWindow {background-color: #f0f2f5; font-family: Arial, sans-serif;}
            QLabel {font-size: 14px; color: #333; margin-bottom: 5px;}
            QTextEdit {border: 1px solid #ccc; border-radius: 8px; padding: 10px; background-color: #fff; font-size: 13px; color: #444;}
            QPushButton {background-color: #007bff; color: white; border: none; border-radius: 8px; padding: 8px 12px; font-size: 13px; font-weight: bold; margin-top: 10px;}
            QPushButton:hover {background-color: #0056b3;}
            QPushButton:disabled {background-color: #6c757d; color: #adb5bd;}
            QMessageBox {background-color: #f0f2f5; font-size: 14px;}
            QLineEdit, QComboBox {border: 1px solid #ccc; border-radius: 8px; padding: 8px; font-size: 13px; background-color: #fff; color: #444;}
            QTreeWidget {border: 1px solid #ccc; border-radius: 8px; background-color: #fff; font-size: 13px; color: #444;}
            QTreeWidget::item {padding: 5px; color: #333;}
            QTreeWidget::item:selected {background-color: #e0f2ff; color: #000;}
            QGroupBox {font-weight: bold; border: 2px solid #ccc; border-radius: 8px; margin-top: 10px; padding-top: 10px; color: #333; background-color: #fff;}
            QGroupBox::title {subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; color: #333;}
        """)

        # Define color styles for the output text
        self.green_style = "color: green; font-weight: bold;"
        self.yellow_style = "color: orange; font-weight: bold;" # Using orange as yellow can be hard to read
        self.red_style = "color: red; font-weight: bold;"
        self.default_style = "color: #444;" # Default text color from QSS


        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_h_layout = QHBoxLayout(self.central_widget)
        self.main_h_layout.setContentsMargins(10, 10, 10, 10)
        self.left_panel_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel_widget)
        self.left_panel_widget.setFixedWidth(self.initial_left_panel_width)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.model_label = QLabel("Phone Model Name:")
        self.left_layout.addWidget(self.model_label)
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., Samsung Galaxy S24 Ultra")
        self.left_layout.addWidget(self.model_input)
        self.input_label = QLabel("Paste phone band information here:")
        self.left_layout.addWidget(self.input_label)
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("e.g., 5G n77, 4G B2, B4...")
        self.input_text.setMinimumHeight(75)
        self.input_text.setMaximumHeight(75)
        self.left_layout.addWidget(self.input_text, stretch=0)
        self.analyze_button = QPushButton("Analyze Bands")
        self.analyze_button.clicked.connect(self.analyze_bands)
        self.left_layout.addWidget(self.analyze_button)
        analysis_group = QGroupBox("Advanced Analysis")
        analysis_layout = QVBoxLayout()
        carrier_layout = QHBoxLayout()
        carrier_layout.addWidget(QLabel("Select Carrier:"))
        self.carrier_selector = QComboBox()
        self.carrier_selector.addItems(["Select Carrier"] + list(self.get_us_carriers().keys()))
        carrier_layout.addWidget(self.carrier_selector)
        analysis_layout.addLayout(carrier_layout)
        self.best_device_button = QPushButton("Find Best Device")
        self.best_device_button.clicked.connect(self.show_best_device)
        analysis_layout.addWidget(self.best_device_button)
        analysis_group.setLayout(analysis_layout)
        self.left_layout.addWidget(analysis_group)
        self.output_label = QLabel("Compatibility Report:")
        self.left_layout.addWidget(self.output_label)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.left_layout.addWidget(self.output_text, stretch=1)
        self.toggle_log_button = QPushButton("Show History")
        self.toggle_log_button.clicked.connect(self.toggle_history_panel)
        self.left_layout.addWidget(self.toggle_log_button)
        self.right_panel_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel_widget)
        self.right_panel_widget.setMinimumWidth(150)
        self.right_panel_widget.setMaximumWidth(self.history_panel_width * 2)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.log_label = QLabel("Comparison History:")
        self.right_layout.addWidget(self.log_label)
        self.log_tree = QTreeWidget()
        self.log_tree.setHeaderLabels(["Phone Model / Date"])
        self.log_tree.itemClicked.connect(self.display_log_entry)
        self.log_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Corrected here
        self.right_layout.addWidget(self.log_tree)
        history_buttons_layout = QVBoxLayout()
        self.compare_button = QPushButton("Compare")
        self.compare_button.clicked.connect(self.compare_multiple_entries)
        self.compare_button.setEnabled(False)
        history_buttons_layout.addWidget(self.compare_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected_entries)
        self.delete_button.setEnabled(False)
        history_buttons_layout.addWidget(self.delete_button)
        self.right_layout.addLayout(history_buttons_layout)
        self.log_tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.comparison_history = []
        self.right_panel_widget.hide()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_panel_widget)
        self.splitter.addWidget(self.right_panel_widget)
        self.splitter.setSizes([self.initial_left_panel_width, 0])
        self.main_h_layout.addWidget(self.splitter)
        self.load_history()

    def get_us_carriers(self):
        return {
            'Verizon': {
                '4G/LTE': {2, 4, 5, 13, 41, 46, 48, 66, 71},
                'Core LTE': {2, 4, 13, 66},
                '5G': {2, 5, 66, 77, 260, 261}
            },
            'AT&T': {
                '4G/LTE': {2, 4, 5, 12, 14, 17, 29, 30, 66, 71},
                'Core LTE': {2, 4, 12, 17, 29},
                '5G': {2, 5, 66, 77, 260}
            },
            'T-Mobile': {
                '4G/LTE': {2, 4, 5, 12, 25, 41, 66, 71},
                'Core LTE': {2, 4, 12, 71},
                '5G': {2, 25, 38, 41, 71, 258, 260, 261}
            }
        }

    def on_selection_changed(self):
        selected_items = self.get_selected_comparison_items()
        self.compare_button.setEnabled(len(selected_items) >= 2)
        self.delete_button.setEnabled(len(selected_items) >= 1)

    def get_selected_comparison_items(self):
        selected_items = self.log_tree.selectedItems()
        comparison_items = []
        for item in selected_items:
            if hasattr(item, 'comparison_data'):
                comparison_items.append(item)
        return comparison_items

    def compare_multiple_entries(self):
        selected_items = self.get_selected_comparison_items()
        if len(selected_items) < 2:
            QMessageBox.warning(self, "Selection Error", "Select 2 or more history entries to compare")
            return
        comparison_data = []
        for item in selected_items:
            comparison_data.append(item.comparison_data)
        dialog = ComparisonDialog(comparison_data, self)
        dialog.exec()

    def delete_selected_entries(self):
        selected_items = self.get_selected_comparison_items()
        if not selected_items:
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(selected_items)} selected entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected_items:
                if item.comparison_data in self.comparison_history:
                    self.comparison_history.remove(item.comparison_data)
                index = self.log_tree.indexOfTopLevelItem(item)
                if index >= 0:
                    self.log_tree.takeTopLevelItem(index)
            self.save_history()

    def show_best_device(self):
        selected_carrier = self.carrier_selector.currentText()
        if selected_carrier == "Select Carrier" or not self.comparison_history:
            QMessageBox.information(self, "Information",
                "Please select a carrier and ensure you have device history to analyze.")
            return
        all_carriers = self.get_us_carriers()
        best_device = self.find_best_device_for_carrier(selected_carrier, all_carriers)
        if best_device:
            score = calculate_compatibility_score(best_device['results'][selected_carrier])
            self.output_text.clear()
            self.output_text.append(f"<span style=\"{self.default_style}\">=== BEST DEVICE ANALYSIS FOR {selected_carrier.upper()} ===</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Best Device: </span><span style=\"{self.green_style}\">{best_device['model']}</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Compatibility Score: </span><span style=\"{self.green_style}\">{score:.1f}</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Analysis Date: </span><span style=\"{self.default_style}\">{best_device['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</span>")
            self.output_text.append("")
            carrier_results = best_device['results'][selected_carrier]
            self.output_text.append(f"<span style=\"{self.default_style}\">--- {selected_carrier} Compatibility Details ---</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Supported LTE Bands: </span><span style=\"{self.green_style}\">{carrier_results['supported_lte']}</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Supported 5G Bands: </span><span style=\"{self.green_style}\">{carrier_results['supported_nr']}</span>")
            
            missing_lte_str = str(carrier_results['missing_lte']) if carrier_results['missing_lte'] else 'None (All supported!)'
            if carrier_results['missing_lte']:
                self.output_text.append(f"<span style=\"{self.default_style}\">Missing LTE Bands: </span><span style=\"{self.yellow_style}\">{missing_lte_str}</span>")
            else:
                self.output_text.append(f"<span style=\"{self.default_style}\">Missing LTE Bands: </span><span style=\"{self.green_style}\">{missing_lte_str}</span>")


            missing_nr_str = str(carrier_results['missing_nr']) if carrier_results['missing_nr'] else 'None (All supported!)'
            if carrier_results['missing_nr']:
                self.output_text.append(f"<span style=\"{self.default_style}\">Missing 5G Bands: </span><span style=\"{self.yellow_style}\">{missing_nr_str}</span>")
            else:
                self.output_text.append(f"<span style=\"{self.default_style}\">Missing 5G Bands: </span><span style=\"{self.green_style}\">{missing_nr_str}</span>")

            if carrier_results['missing_core_lte']:
                self.output_text.append(f"<span style=\"{self.red_style}\">⚠️ CRITICAL: Missing Core LTE Bands: {carrier_results['missing_core_lte']}</span>")
            else:
                self.output_text.append(f"<span style=\"{self.green_style}\">✅ All Core LTE Bands Supported</span>")
            self.output_text.append("")
            self.output_text.append(f"<span style=\"{self.default_style}\">=== COMPARISON WITH OTHER DEVICES ===</span>")
            all_scores = []
            for entry in self.comparison_history:
                if selected_carrier in entry['results']:
                    entry_score = calculate_compatibility_score(entry['results'][selected_carrier])
                    all_scores.append((entry['model'], entry_score))
            all_scores.sort(key=lambda x: x[1], reverse=True)
            for i, (model, score) in enumerate(all_scores[:5], 1):
                status = "👑 BEST" if i == 1 else f"#{i}"
                self.output_text.append(f"<span style=\"{self.default_style}\">{status} {model}: </span><span style=\"{self.green_style}\">{score:.1f} points</span>")
        else:
            QMessageBox.information(self, "No Data",
                f"No compatible devices found for {selected_carrier} in your history.")

    def find_best_device_for_carrier(self, carrier, all_carriers):
        best_score = -1
        best_device = None
        for entry in self.comparison_history:
            if carrier in entry['results']:
                score = calculate_compatibility_score(entry['results'][carrier])
                if score > best_score:
                    best_score = score
                    best_device = entry
        return best_device

    def closeEvent(self, event):
        self.save_history()
        event.accept()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    loaded_history = json.load(f)
                for entry_data in loaded_history:
                    entry_data['timestamp'] = datetime.strptime(entry_data['timestamp'], "%Y-%m-%d %H:%M:%S")
                    self.comparison_history.append(entry_data)
                    self.add_log_entry_to_tree(entry_data)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Error loading history: {e}")

    def save_history(self):
        serializable_history = []
        for entry_data in self.comparison_history:
            serializable_entry = entry_data.copy()
            serializable_entry['timestamp'] = serializable_entry['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            serializable_history.append(serializable_entry)
        try:
            # Ensure the Downloads folder exists
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, 'w') as f:
                json.dump(serializable_history, f, indent=4)
            print(f"History saved to {HISTORY_FILE}")
        except IOError as e:
            QMessageBox.critical(self, "Save History Error", f"Could not save history: {e}")

    def toggle_history_panel(self):
        is_visible = self.right_panel_widget.isVisible()
        if not is_visible:
            self.toggle_log_button.setText("Hide History")
            self.right_panel_widget.show()
            self.setMaximumWidth(16777215)
            new_width = self.initial_left_panel_width + self.history_panel_width + self.main_h_layout.contentsMargins().left() + self.main_h_layout.contentsMargins().right()
            self.resize(new_width, self.height())
            self.splitter.setSizes([self.initial_left_panel_width, self.history_panel_width])
            self.setMinimumWidth(new_width)
        else:
            self.toggle_log_button.setText("Show History")
            self.right_panel_widget.hide()
            new_width = self.initial_left_panel_width + self.main_h_layout.contentsMargins().left() + self.main_h_layout.contentsMargins().right()
            self.resize(new_width, self.height())
            self.splitter.setSizes([self.initial_left_panel_width, 0])
            self.setMinimumWidth(new_width)
            self.setMaximumWidth(new_width)

    def analyze_bands(self):
        phone_info_text = self.input_text.toPlainText().strip()
        phone_model = self.model_input.text().strip()
        if not phone_model:
            phone_model = "Unknown Model"
        if not phone_info_text:
            QMessageBox.warning(self, "Input Error", "Please paste phone band information into the text area.")
            return
        phone_lte_bands_list, phone_nr_bands_list = parse_phone_bands(phone_info_text)
        is_duplicate = False
        for entry in self.comparison_history:
            if (entry['model'] == phone_model and
                entry['phone_lte'] == phone_lte_bands_list and
                entry['phone_5g'] == phone_nr_bands_list):
                is_duplicate = True
                break
        if is_duplicate:
            QMessageBox.information(self, "Duplicate Entry", "This exact phone model and band combination has already been analyzed and logged.")
            comparison_results = compare_phone_to_carrier(set(phone_lte_bands_list), set(phone_nr_bands_list), self.get_us_carriers())
            self.format_report_for_display(comparison_results, phone_lte_bands_list, phone_nr_bands_list, phone_model)
            return
        phone_lte_bands = set(phone_lte_bands_list)
        phone_nr_bands = set(phone_nr_bands_list)
        if not phone_lte_bands and not phone_nr_bands:
            self.output_text.clear()
            self.output_text.append(f"<span style=\"{self.default_style}\">--- Parsing Phone Bands ---</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Detected Phone LTE Bands: </span><span style=\"{self.yellow_style}\">{phone_lte_bands_list if phone_lte_bands_list else 'None'}</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Detected Phone 5G Bands: </span><span style=\"{self.yellow_style}\">{phone_nr_bands_list if phone_nr_bands_list else 'None'}</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">No LTE or 5G bands could be extracted from the provided text.</span>")
            self.output_text.append(f"<span style=\"{self.default_style}\">Please ensure the text contains band numbers in formats like 'B1', 'Band 2', 'LTE 66', or 'n41'.</span>")
            return
        comparison_results = compare_phone_to_carrier(phone_lte_bands, phone_nr_bands, self.get_us_carriers())
        timestamp = datetime.now()
        log_entry_data = {
            'model': phone_model,
            'timestamp': timestamp,
            'phone_lte': phone_lte_bands_list,
            'phone_5g': phone_nr_bands_list,
            'results': comparison_results
        }
        self.comparison_history.append(log_entry_data)
        self.add_log_entry_to_tree(log_entry_data)
        self.format_report_for_display(comparison_results, phone_lte_bands_list, phone_nr_bands_list, phone_model)

    def add_log_entry_to_tree(self, log_data):
        model_name = log_data['model']
        formatted_date = log_data['timestamp'].strftime("%b '%y")
        display_text = f"{model_name} - {formatted_date}"
        parent_item = QTreeWidgetItem(self.log_tree, [display_text])
        parent_item.comparison_data = log_data
        self.log_tree.addTopLevelItem(parent_item)

    def display_log_entry(self, item, column):
        if hasattr(item, 'comparison_data'):
            data_to_display = item.comparison_data
        else:
            return
        self.output_text.clear()
        self.format_report_for_display(
            data_to_display['results'],
            data_to_display['phone_lte'],
            data_to_display['phone_5g'],
            data_to_display['model']
        )

    def format_report_for_display(self, comparison_results, phone_lte_bands_list, phone_nr_bands_list, phone_model):
        self.output_text.clear()
        self.output_text.append(f"<span style=\"{self.default_style}\">=== COMPATIBILITY REPORT FOR {phone_model.upper()} ===</span>")
        self.output_text.append(f"<span style=\"{self.default_style}\">Detected Phone LTE Bands: </span><span style=\"{self.green_style}\">{phone_lte_bands_list if phone_lte_bands_list else 'None'} ({len(phone_lte_bands_list)} total)</span>")
        self.output_text.append(f"<span style=\"{self.default_style}\">Detected Phone 5G Bands: </span><span style=\"{self.green_style}\">{phone_nr_bands_list if phone_nr_bands_list else 'None'} ({len(phone_nr_bands_list)} total)</span>")
        self.output_text.append("")
        carrier_scores = []
        for carrier, data in comparison_results.items():
            score = calculate_compatibility_score(data)
            carrier_scores.append((carrier, score, data))
        carrier_scores.sort(key=lambda x: x[1], reverse=True)
        self.output_text.append(f"<span style=\"{self.default_style}\">=== CARRIER COMPATIBILITY RANKING ===</span>")
        for i, (carrier, score, data) in enumerate(carrier_scores, 1):
            status_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📱"
            lte_count = len(data['supported_lte'])
            nr_count = len(data['supported_nr'])
            self.output_text.append(f"<span style=\"{self.default_style}\">{status_emoji} #{i} {carrier}: </span><span style=\"{self.green_style}\">{score:.1f} points ({lte_count} LTE + {nr_count} 5G)</span>")
        self.output_text.append("")
        self.output_text.append(f"<span style=\"{self.default_style}\">=== DETAILED CARRIER ANALYSIS ===</span>")
        for i, (carrier, score, data) in enumerate(carrier_scores, 1):
            rank_indicator = f"#{i} " + ("🥇 BEST MATCH" if i == 1 else "🥈 EXCELLENT" if i == 2 else "🥉 GOOD" if i == 3 else "COMPATIBLE")
            self.output_text.append(f"<span style=\"{self.default_style}\">----- {carrier} - {rank_indicator} -----</span>")
            lte_supported = len(data['supported_lte'])
            nr_supported = len(data['supported_nr'])
            missing_core = len(data['missing_core_lte'])
            self.output_text.append(f"<span style=\"{self.default_style}\">Compatibility Score: </span><span style=\"{self.green_style}\">{score:.1f} points ({lte_supported} LTE×2 + {nr_supported} 5G×1 - {missing_core} Core×2)</span>")
            
            supported_lte_str = str(data['supported_lte']) if data['supported_lte'] else 'None'
            self.output_text.append(f"<span style=\"{self.default_style}\">✅ Supported LTE Bands: </span><span style=\"{self.green_style}\">{supported_lte_str}</span>")
            
            missing_lte_str = str(data['missing_lte']) if data['missing_lte'] else 'None (All supported!)'
            if data['missing_lte']:
                self.output_text.append(f"<span style=\"{self.default_style}\">❌ Missing LTE Bands: </span><span style=\"{self.yellow_style}\">{missing_lte_str}</span>")
            else:
                self.output_text.append(f"<span style=\"{self.default_style}\">❌ Missing LTE Bands: </span><span style=\"{self.green_style}\">{missing_lte_str}</span>")

            if data['missing_core_lte']:
                critical_missing_str = str(data['missing_core_lte'])
                self.output_text.append(f"<span style=\"{self.red_style}\">⚠️ CRITICAL: Missing Core LTE Bands: {critical_missing_str}</span>")
            else:
                self.output_text.append(f"<span style=\"{self.green_style}\">✅ All Core LTE Bands Supported</span>")
            
            supported_nr_str = str(data['supported_nr']) if data['supported_nr'] else 'None'
            self.output_text.append(f"<span style=\"{self.default_style}\">📶 Supported 5G Bands: </span><span style=\"{self.green_style}\">{supported_nr_str}</span>")
            
            missing_nr_str = str(data['missing_nr']) if data['missing_nr'] else 'None (All supported!)'
            if data['missing_nr']:
                self.output_text.append(f"<span style=\"{self.default_style}\">📵 Missing 5G Bands: </span><span style=\"{self.yellow_style}\">{missing_nr_str}</span>")
            else:
                self.output_text.append(f"<span style=\"{self.default_style}\">📵 Missing 5G Bands: </span><span style=\"{self.green_style}\">{missing_nr_str}</span>")
            
            self.output_text.append(f"<span style=\"{self.default_style}\">" + "-" * (len(carrier) + 25) + "</span>")
        self.output_text.append("")
        self.output_text.append(f"<span style=\"{self.default_style}\">🎉 Analysis complete! Use 'Show History' to compare with other devices.</span>")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = BandCheckerApp()
    main_window.show()
    sys.exit(app.exec())
