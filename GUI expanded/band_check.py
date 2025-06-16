import re
import sys
import json
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QLabel, QTextEdit, QPushButton, QMessageBox,
    QHBoxLayout, QSplitter, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView # Import QAbstractItemView for selection modes
)
from PyQt6.QtGui import QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt, QSize # Import QSize for fixed size hints

# Define the file path for history
HISTORY_FILE = 'band_checker_history.json'

def parse_phone_bands(text):
    """
    Parses the input text to extract 4G/LTE and 5G band numbers.
    This version is more robust in handling various formats of band listings
    by using section-aware parsing and stricter regex for LTE bands.
    """
    lte_bands = set()
    nr_bands = set() # 5G New Radio bands

    # --- 5G Band Extraction ---
    # Look for 'n' followed by digits anywhere in the text.
    # This handles "n28A" as "n28" which is the standard interpretation (n-bands are numeric).
    nr_matches = re.findall(r'n(\d+)(?:[a-zA-Z])?', text, re.IGNORECASE)
    for band_str in nr_matches:
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
                    # Removed `band_num not in nr_bands` as LTE and 5G can share band numbers.
                    if 1 <= band_num <= 100: # Common LTE bands are typically <= 71, but 100 is a safe upper bound.
                        lte_bands.add(band_num)
                except ValueError:
                    pass

    return sorted(list(lte_bands)), sorted(list(nr_bands))

def compare_phone_to_carrier(phone_lte_bands, phone_nr_bands, carrier_data):
    """
    Comparisons the phone's bands against a specific carrier's bands.
    """
    results = {}
    for carrier_name, bands_info in carrier_data.items():
        carrier_lte = set(bands_info['4G/LTE'])
        carrier_nr = set(bands_info['5G'])
        carrier_core_lte = set(bands_info['Core LTE'])

        # Supported bands
        supported_lte = phone_lte_bands.intersection(carrier_lte)
        supported_nr = phone_nr_bands.intersection(carrier_nr)

        # Missing bands
        missing_lte = carrier_lte - phone_lte_bands
        missing_nr = carrier_nr - phone_nr_bands

        # Missing core bands
        missing_core_lte = carrier_core_lte.intersection(missing_lte)

        results[carrier_name] = {
            'supported_lte': sorted(list(supported_lte)),
            'supported_nr': sorted(list(supported_nr)),
            'missing_lte': sorted(list(missing_lte)),
            'missing_nr': sorted(list(missing_nr)),
            'missing_core_lte': sorted(list(missing_core_lte))
        }

    return results

class BandCheckerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cell Phone Band Compatibility Checker")

        # Initial window size for main content (left panel)
        self.initial_left_panel_width = 820
        self.initial_height = 700
        self.history_panel_width = 300 # Desired width for the history panel when visible

        # Calculate total initial width including margins (10px left + 10px right = 20px)
        total_initial_width = self.initial_left_panel_width + 20

        # Set initial geometry to match the "hidden" state (only left panel visible)
        self.setGeometry(100, 100, total_initial_width, self.initial_height)
        self.setMinimumSize(total_initial_width, self.initial_height) # Prevent shrinking below initial size
        # Initially, set max width to total_initial_width to restrict it
        self.setMaximumWidth(total_initial_width)

        # Apply modern QSS (Qt Style Sheet) for a fresh look
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f2f5; /* Light gray background */
                font-family: Arial, sans-serif;
            }
            QLabel {
                font-size: 14px;
                color: #333;
                margin-bottom: 5px;
            }
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 8px; /* Rounded corners */
                padding: 10px;
                background-color: #fff;
                font-size: 13px;
                color: #444;
            }
            QPushButton {
                background-color: #007bff; /* Primary blue color */
                color: white;
                border: none;
                border-radius: 8px; /* Ensure rounded corners */
                padding: 10px 15px; /* Reduced horizontal padding from 20px to 15px */
                font-size: 15px;
                font-weight: bold;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #0056b3; /* Darker blue on hover */
            }
            QMessageBox {
                background-color: #f0f2f5;
                font-size: 14px;
            }
            QLineEdit { /* Styling for QLineEdit to match QTextEdit */
                border: 1px solid #ccc;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
                background-color: #fff; /* White background */
                color: #444; /* Black text */
            }
            QTreeWidget {
                border: 1px solid #ccc;
                border-radius: 8px;
                background-color: #fff;
                font-size: 13px;
                color: #444;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QTreeWidget::item:selected {
                background-color: #e0f2ff; /* Light blue on selection */
                color: #000;
            }
        """)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Main layout: Horizontal layout to split left (app content) and right (log)
        self.main_h_layout = QHBoxLayout(self.central_widget)
        # Reduce margins for the main horizontal layout to give more space to widgets
        self.main_h_layout.setContentsMargins(10, 10, 10, 10)

        # --- Left Panel (Main Application Content) ---
        self.left_panel_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel_widget)

        # Set a fixed width for the left panel. This is key for its stable size.
        self.left_panel_widget.setFixedWidth(self.initial_left_panel_width)

        # Reduce internal margins for the left panel's layout
        self.left_layout.setContentsMargins(0, 0, 0, 0) # Remove internal margins

        # Phone Model Input
        self.model_label = QLabel("Phone Model Name:")
        self.left_layout.addWidget(self.model_label)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., Samsung Galaxy S24 Ultra")
        self.left_layout.addWidget(self.model_input)

        # Input Label
        self.input_label = QLabel("Paste phone band information here:")
        self.left_layout.addWidget(self.input_label)

        # Input Text Area - Fixed height (75px)
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("e.g., 5G n77, 4G B2, B4...")
        self.input_text.setMinimumHeight(75)
        self.input_text.setMaximumHeight(75) # Set maximum height to fix its size
        self.left_layout.addWidget(self.input_text, stretch=0) # stretch=0 prevents it from taking extra space

        # Analyze Button
        self.analyze_button = QPushButton("Analyze Bands")
        self.analyze_button.clicked.connect(self.analyze_bands)
        self.left_layout.addWidget(self.analyze_button)

        # Output Label
        self.output_label = QLabel("Compatibility Report:")
        self.left_layout.addWidget(self.output_label)

        # Output Text Area - Expands/shrinks vertically with window resize
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True) # Make it read-only
        self.left_layout.addWidget(self.output_text, stretch=1) # stretch=1 makes it take available space

        # Toggle History Button (added to left layout for visibility)
        self.toggle_log_button = QPushButton("Show History")
        self.toggle_log_button.clicked.connect(self.toggle_history_panel)
        self.left_layout.addWidget(self.toggle_log_button) # Add it to the left layout

        # --- Right Panel (Log / History) ---
        self.right_panel_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel_widget)

        # Set a minimum width for the history panel so it doesn't disappear when resized
        self.right_panel_widget.setMinimumWidth(150) # Allow shrinking down to 150px
        self.right_panel_widget.setMaximumWidth(self.history_panel_width * 2) # Arbitrary max for user resizing

        # Remove internal margins for the right panel's layout
        self.right_layout.setContentsMargins(0, 0, 0, 0) # Remove internal margins

        self.log_label = QLabel("Comparison History:")
        self.right_layout.addWidget(self.log_label)

        self.log_tree = QTreeWidget()
        self.log_tree.setHeaderLabels(["Phone Model / Date"])
        self.log_tree.itemClicked.connect(self.display_log_entry) # Connect signal to display detail
        # Enable multi-selection for comparison
        self.log_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Corrected here
        self.right_layout.addWidget(self.log_tree)

        # New: Compare Selected Phones Button
        self.compare_button = QPushButton("Compare Selected Phones")
        self.compare_button.clicked.connect(self.compare_selected_phones)
        self.right_layout.addWidget(self.compare_button)


        # Store log data (in-memory for now)
        self.comparison_history = []

        # Hide the right panel by default
        self.right_panel_widget.hide()

        # --- QSplitter to combine left and right panels ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal) # Horizontal splitter
        self.splitter.addWidget(self.left_panel_widget)
        self.splitter.addWidget(self.right_panel_widget)

        # Initial splitter sizes: left panel takes its fixed width, right panel is 0
        self.splitter.setSizes([self.initial_left_panel_width, 0])

        self.main_h_layout.addWidget(self.splitter) # Add the splitter to the main horizontal layout

        # Pre-set US carrier band data
        self.us_carriers = {
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

        # Load history on startup
        self.load_history()

    def closeEvent(self, event):
        """Overrides the close event to save history before closing."""
        self.save_history()
        event.accept() # Accept the close event

    def load_history(self):
        """Loads comparison history from the JSON file."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    loaded_history = json.load(f)
                for entry_data in loaded_history:
                    # Convert timestamp string back to datetime object
                    entry_data['timestamp'] = datetime.strptime(entry_data['timestamp'], "%Y-%m-%d %H:%M:%S")
                    self.comparison_history.append(entry_data)
                    self.add_log_entry_to_tree(entry_data)
            except (IOError, json.JSONDecodeError) as e:
                # Silently fail or log to console, do not show QMessageBox
                print(f"Error loading history: {e}")
        # Do not show QMessageBox if no history found or on successful load

    def save_history(self):
        """Saves current comparison history to a JSON file."""
        serializable_history = []
        for entry_data in self.comparison_history:
            # Convert datetime object to string for JSON serialization
            serializable_entry = entry_data.copy()
            serializable_entry['timestamp'] = serializable_entry['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            serializable_history.append(serializable_entry)

        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(serializable_history, f, indent=4)
            print(f"History saved to {HISTORY_FILE}")
        except IOError as e:
            QMessageBox.critical(self, "Save History Error", f"Could not save history: {e}")

    def toggle_history_panel(self):
        is_visible = self.right_panel_widget.isVisible()

        if not is_visible: # Was hidden, now showing
            self.toggle_log_button.setText("Hide History")
            self.right_panel_widget.show()

            # Remove maximum width constraint to allow expansion
            self.setMaximumWidth(16777215) # Max int for effectively unlimited width

            # Resize the main window to include the history panel's width
            new_width = self.initial_left_panel_width + self.history_panel_width + self.main_h_layout.contentsMargins().left() + self.main_h_layout.contentsMargins().right()
            self.resize(new_width, self.height())

            # Ensure the splitter distributes space correctly: fixed left, history width for right
            self.splitter.setSizes([self.initial_left_panel_width, self.history_panel_width])

            # Set minimum width for the entire window when history is visible
            self.setMinimumWidth(new_width) # Min width is now the expanded width

        else: # Was showing, now hiding
            self.toggle_log_button.setText("Show History")
            self.right_panel_widget.hide()

            # Resize the main window back to its initial width (left panel only)
            new_width = self.initial_left_panel_width + self.main_h_layout.contentsMargins().left() + self.main_h_layout.contentsMargins().right()
            self.resize(new_width, self.height())

            # Ensure the splitter hides the right panel
            self.splitter.setSizes([self.initial_left_panel_width, 0])

            # Reset minimum width to the initial state
            self.setMinimumWidth(new_width)

            # Set maximum width back to the initial left panel width to restrict it
            self.setMaximumWidth(new_width)

    def analyze_bands(self):
        phone_info_text = self.input_text.toPlainText().strip()
        phone_model = self.model_input.text().strip()

        if not phone_model:
            phone_model = "Unknown Model"

        if not phone_info_text:
            QMessageBox.warning(self, "Input Error", "Please paste phone band information into the text area.")
            return

        # Parse phone bands from the input text
        phone_lte_bands_list, phone_nr_bands_list = parse_phone_bands(phone_info_text)

        # Check for duplicates before proceeding
        is_duplicate = False
        for entry in self.comparison_history:
            # Compare lists for equality for phone_lte and phone_5g bands
            if (entry['model'] == phone_model and
                entry['phone_lte'] == phone_lte_bands_list and
                entry['phone_5g'] == phone_nr_bands_list):
                is_duplicate = True
                break

        if is_duplicate:
            QMessageBox.information(self, "Duplicate Entry", "This exact phone model and band combination has already been analyzed and logged.")
            # Still display the report for the duplicate in the main area
            comparison_results = compare_phone_to_carrier(set(phone_lte_bands_list), set(phone_nr_bands_list), self.us_carriers)
            self.format_report_for_display(comparison_results, phone_lte_bands_list, phone_nr_bands_list, phone_model)
            return

        # If not a duplicate, proceed with full analysis and logging
        phone_lte_bands = set(phone_lte_bands_list)
        phone_nr_bands = set(phone_nr_bands_list)

        if not phone_lte_bands and not phone_nr_bands:
            self.output_text.clear()
            self.output_text.append("--- Parsing Phone Bands ---")
            self.output_text.append(f"Detected Phone LTE Bands: {phone_lte_bands_list if phone_lte_bands_list else 'None'}")
            self.output_text.append(f"Detected Phone 5G Bands: {phone_nr_bands_list if phone_nr_bands_list else 'None'}")
            self.output_text.append("No LTE or 5G bands could be extracted from the provided text.")
            self.output_text.append("Please ensure the text contains band numbers in formats like 'B1', 'Band 2', 'LTE 66', or 'n41'.")
            return

        # Compare phone bands with carrier bands
        comparison_results = compare_phone_to_carrier(phone_lte_bands, phone_nr_bands, self.us_carriers)

        # Add to history
        timestamp = datetime.now() # Store datetime object
        log_entry_data = {
            'model': phone_model,
            'timestamp': timestamp,
            'phone_lte': phone_lte_bands_list,
            'phone_5g': phone_nr_bands_list,
            'results': comparison_results
        }

        self.comparison_history.append(log_entry_data)
        self.add_log_entry_to_tree(log_entry_data)

        # Display the current analysis result in the main output area
        self.format_report_for_display(comparison_results, phone_lte_bands_list, phone_nr_bands_list, phone_model)

    def add_log_entry_to_tree(self, log_data):
        entry_text = f"{log_data['model']} ({log_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')})"
        parent_item = QTreeWidgetItem(self.log_tree, [entry_text])

        # Store the raw data with the parent item for later retrieval
        parent_item.comparison_data = log_data # Store the entire log_data dict

        self.log_tree.addTopLevelItem(parent_item)

    def display_log_entry(self, item, column):
        # This function is called when any item in the QTreeWidget is clicked.
        # We want to display the full report when the parent item is clicked.
        if hasattr(item, 'comparison_data'): # If the clicked item is a top-level parent
            data_to_display = item.comparison_data
        else:
            return # Not a relevant item for displaying the report

        self.output_text.clear()
        self.format_report_for_display(
            data_to_display['results'],
            data_to_display['phone_lte'],
            data_to_display['phone_5g'],
            data_to_display['model']
        )

    def format_report_for_display(self, comparison_results, phone_lte_bands_list, phone_nr_bands_list, phone_model):
        self.output_text.clear() # Clear before displaying

        self.output_text.append(f"--- Report for {phone_model} ---")
        self.output_text.append(f"Detected Phone LTE Bands: {phone_lte_bands_list if phone_lte_bands_list else 'None'}")
        self.output_text.append(f"Detected Phone 5G Bands: {phone_nr_bands_list if phone_nr_bands_list else 'None'}")
        self.output_text.append("--- Carrier Compatibility Report ---")

        for carrier, data in comparison_results.items():
            self.output_text.append(f"----- {carrier} -----")

            # Supported LTE Bands
            supported_lte_str = str(data['supported_lte']) if data['supported_lte'] else 'None'
            self.output_text.append(f" Supported LTE Bands: {supported_lte_str}")

            # Missing LTE Bands
            missing_lte_str = str(data['missing_lte']) if data['missing_lte'] else 'None (All supported!)'
            self.output_text.append(f" Missing LTE Bands: {missing_lte_str}")

            # Critical Missing Core LTE Bands
            if data['missing_core_lte']:
                critical_missing_str = str(data['missing_core_lte'])
                self.output_text.append(f" !!! CRITICAL: Missing Core LTE Bands: {critical_missing_str} !!!")
            else:
                self.output_text.append(f" All Core LTE Bands are Supported.")

            # Supported 5G Bands
            supported_nr_str = str(data['supported_nr']) if data['supported_nr'] else 'None'
            self.output_text.append(f" Supported 5G Bands: {supported_nr_str}")

            # Missing 5G Bands
            missing_nr_str = str(data['missing_nr']) if data['missing_nr'] else 'None (All supported!)'
            self.output_text.append(f" Missing 5G Bands: {missing_nr_str}")

            self.output_text.append("-" * (len(carrier) + 12))

        self.output_text.append("Analysis complete. Thank you for using the tool!")

    def compare_selected_phones(self):
        """
        Compares the band support of multiple selected phones from the history.
        """
        selected_items = self.log_tree.selectedItems()
        selected_phones_data = []

        for item in selected_items:
            if hasattr(item, 'comparison_data'):
                selected_phones_data.append(item.comparison_data)

        if len(selected_phones_data) < 2:
            QMessageBox.warning(self, "Comparison Error", "Please select at least two phones from the history to compare.")
            return

        self.format_comparison_report_for_display(selected_phones_data)

    def format_comparison_report_for_display(self, phones_data_list):
        """
        Generates and displays a comparison report for multiple phones.
        """
        self.output_text.clear()
        self.output_text.append("--- Multi-Phone Comparison Report ---")
        self.output_text.append("\nSummary of Band Support:")

        comparison_metrics = [] # To store metrics for each phone for easier comparison

        # Calculate metrics for each selected phone
        for phone_data in phones_data_list:
            model = phone_data['model']
            detected_lte = set(phone_data['phone_lte'])
            detected_nr = set(phone_data['phone_5g'])
            comparison_results = phone_data['results']

            overall_supported_lte_bands = set()
            overall_supported_nr_bands = set()
            total_critical_missing_lte_bands = 0

            for carrier, data in comparison_results.items():
                overall_supported_lte_bands.update(set(data['supported_lte']))
                overall_supported_nr_bands.update(set(data['supported_nr']))
                total_critical_missing_lte_bands += len(data['missing_core_lte'])

            # Store metrics for this phone
            phone_metrics = {
                'model': model,
                'detected_lte_count': len(detected_lte),
                'detected_nr_count': len(detected_nr),
                'overall_supported_lte_count': len(overall_supported_lte_bands),
                'overall_supported_nr_count': len(overall_supported_nr_bands),
                'total_critical_missing_lte_bands': total_critical_missing_lte_bands,
                'overall_supported_lte': sorted(list(overall_supported_lte_bands)),
                'overall_supported_nr': sorted(list(overall_supported_nr_bands)),
            }
            comparison_metrics.append(phone_metrics)

            # Display individual phone summary within the comparison report
            self.output_text.append(f"\n--- {model} ---")
            self.output_text.append(f"  Detected LTE Bands: {sorted(list(detected_lte)) if detected_lte else 'None'}")
            self.output_text.append(f"  Detected 5G Bands: {sorted(list(detected_nr)) if detected_nr else 'None'}")
            self.output_text.append(f"  Overall Supported LTE Bands (across all carriers): {phone_metrics['overall_supported_lte']}")
            self.output_text.append(f"  Overall Supported 5G Bands (across all carriers): {phone_metrics['overall_supported_nr']}")
            self.output_text.append(f"  Total Critical Missing Core LTE Bands (summed across carriers): {total_critical_missing_lte_bands}")


        # Determine the "best" phone based on metrics
        # Criteria:
        # 1. Max overall supported LTE bands
        # 2. Max overall supported 5G bands
        # 3. Min total critical missing LTE bands

        best_lte_phone = None
        max_lte_bands = -1
        best_nr_phone = None
        max_nr_bands = -1
        best_core_lte_phone = None
        min_critical_bands = float('inf')

        for phone in comparison_metrics:
            if phone['overall_supported_lte_count'] > max_lte_bands:
                max_lte_bands = phone['overall_supported_lte_count']
                best_lte_phone = phone['model']
            elif phone['overall_supported_lte_count'] == max_lte_bands and best_lte_phone:
                best_lte_phone += f", {phone['model']}" # In case of a tie

            if phone['overall_supported_nr_count'] > max_nr_bands:
                max_nr_bands = phone['overall_supported_nr_count']
                best_nr_phone = phone['model']
            elif phone['overall_supported_nr_count'] == max_nr_bands and best_nr_phone:
                best_nr_phone += f", {phone['model']}" # In case of a tie

            if phone['total_critical_missing_lte_bands'] < min_critical_bands:
                min_critical_bands = phone['total_critical_missing_lte_bands']
                best_core_lte_phone = phone['model']
            elif phone['total_critical_missing_lte_bands'] == min_critical_bands and best_core_lte_phone:
                best_core_lte_phone += f", {phone['model']}" # In case of a tie

        self.output_text.append("\n--- Overall Best Performers (among selected phones) ---")
        if best_lte_phone:
            self.output_text.append(f"Best for Overall Supported LTE Bands: {best_lte_phone} (Supported {max_lte_bands} unique bands)")
        if best_nr_phone:
            self.output_text.append(f"Best for Overall Supported 5G Bands: {best_nr_phone} (Supported {max_nr_bands} unique bands)")
        if best_core_lte_phone is not None: # Can be 0 critical missing
            self.output_text.append(f"Best for Critical Core LTE Coverage (fewest missing): {best_core_lte_phone} ({min_critical_bands} total critical missing bands)")

        self.output_text.append("\nDetailed Carrier-Specific Comparison for Selected Phones:")

        # Detailed carrier comparison for each selected phone
        for carrier_name in self.us_carriers.keys():
            self.output_text.append(f"\n===== Carrier: {carrier_name} =====")
            for phone_data in phones_data_list:
                model = phone_data['model']
                data = phone_data['results'].get(carrier_name)
                if data:
                    self.output_text.append(f"  --- {model} for {carrier_name} ---")
                    self.output_text.append(f"   Supported LTE: {data['supported_lte'] if data['supported_lte'] else 'None'}")
                    self.output_text.append(f"   Missing LTE: {data['missing_lte'] if data['missing_lte'] else 'None (All supported!)'}")
                    if data['missing_core_lte']:
                        self.output_text.append(f"   !!! CRITICAL Missing Core LTE: {data['missing_core_lte']} !!!")
                    else:
                        self.output_text.append(f"   All Core LTE Bands are Supported.")
                    self.output_text.append(f"   Supported 5G: {data['supported_nr'] if data['supported_nr'] else 'None'}")
                    self.output_text.append(f"   Missing 5G: {data['missing_nr'] if data['missing_nr'] else 'None (All supported!)'}")
                else:
                    self.output_text.append(f"  --- {model} --- (No data for {carrier_name})")


        self.output_text.append("\nComparison complete. Select more phones or analyze new ones!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = BandCheckerApp()
    main_window.show()
    sys.exit(app.exec())
