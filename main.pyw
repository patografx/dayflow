import ctypes
import json
import os
import sys
import winreg
from datetime import datetime

from PyQt5.QtCore import QPropertyAnimation, QSize, Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

# Function to change wallpaper
def set_wallpaper(image_path):
    ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)

class HoverLabel(QLabel):
    def __init__(self, overlay, fade_in, fade_out, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.overlay = overlay
        self.fade_in = fade_in
        self.fade_out = fade_out

    def enterEvent(self, event):
        self.overlay.setVisible(True)
        self.fade_out.stop()
        self.fade_in.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.fade_in.stop()
        self.fade_out.start()
        self.fade_out.finished.connect(lambda: self.overlay.setVisible(False))
        super().leaveEvent(event)


class HoverButton(QPushButton):
    def __init__(self, overlay, fade_in, fade_out, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.overlay = overlay
        self.fade_in = fade_in
        self.fade_out = fade_out

    def enterEvent(self, event):
        self.overlay.setVisible(True)
        self.fade_out.stop()
        self.fade_in.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.fade_in.stop()
        self.fade_out.start()
        self.fade_out.finished.connect(lambda: self.overlay.setVisible(False))
        super().leaveEvent(event)


class ClickableLabel(QLabel):
    def __init__(self, row, on_click, is_thumbnail=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.row = row
        self.on_click = on_click
        self.is_thumbnail = is_thumbnail  # Flag to differentiate thumbnail from time slot

        if self.is_thumbnail:
            # Add an opacity effect only for thumbnails
            self.opacity_effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self.opacity_effect)
            self.opacity_effect.setOpacity(1.0)  # Default opacity (fully visible)

    def enterEvent(self, event):
        if self.is_thumbnail:
            # Reduce opacity on hover for thumbnails
            self.opacity_effect.setOpacity(0.7)  # Slightly transparent
        else:
            # Change background color for time slots
            self.setStyleSheet("background-color: #555;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.is_thumbnail:
            # Restore opacity when hover ends for thumbnails
            self.opacity_effect.setOpacity(1.0)  # Fully visible
        else:
            # Reset background color for time slots
            self.setStyleSheet("")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if callable(self.on_click):
            self.on_click(self.row)
        super().mousePressEvent(event)


class BackgroundChangerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dayflow - Wallpaper Scheduler")
        self.setWindowIcon(QIcon(os.path.join("assets", "dayflow.png")))
        self.setFixedSize(480, 400)  # Set a fixed size for the window
        self.setStyleSheet(self.get_dark_theme())  # Apply dark mode theme

        self.images = []  # Stores tuples of (image_path, time_slot)
        self.hide_on_minimize = False  # Default: not hiding
        self.force_exit = False  # Flag to track if the app should force exit

        # System tray setup
        self.tray_icon = QSystemTrayIcon(
            QIcon(os.path.join("assets", "dayflow.png")), self
        )
        self.tray_icon.setToolTip("Dayflow - Wallpaper Scheduler")
        self.tray_icon.activated.connect(
            self.on_tray_icon_activated
        )  # Handle left-click on tray icon
        tray_menu = QMenu()

        # Show action
        restore_action = tray_menu.addAction("Show")
        restore_action.triggered.connect(self.show)

        # Exit action
        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.exit_application)  # Connect to a new method

        self.tray_icon.setContextMenu(tray_menu)

        # Main layout
        main_layout = QVBoxLayout()

        # Table for displaying images and time slots
        self.table = QTableWidget(0, 4)  # Four columns now
        self.table.setHorizontalHeaderLabels(
            ["Wallpaper", "File Name", "Start Time", ""]
        )
        self.table.horizontalHeader().setStretchLastSection(
            False
        )  # Disable stretching the last column
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )  # Thumbnail column resizes to content
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )  # Wallpaper column stretches
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )  # Time Slot column resizes to content
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )  # Time Slot column resizes to content
        self.table.setStyleSheet(
            """
            QHeaderView::section {
            background-color: #444;
            color: white;
            padding: 5px;
            border-right: 1px solid #3a3a3a;  /* Add a separator between headers */
            }
            QHeaderView::section:last-of-type {
            border-right: none;  /* Remove the separator for the last header */
            }
            QTableWidget::item:selected {
            background-color: transparent;  /* Prevent blue selection background */
            }
        """
        )
        self.table.setIconSize(QSize(65, 65))  # Set icon size to match row height
        self.table.verticalHeader().setDefaultSectionSize(65)  # Set row height to 65px
        self.table.verticalHeader().setVisible(False)  # Hide the row numbers
        self.table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )  # Prevent editing directly in the table
        self.table.setSelectionMode(
            QTableWidget.NoSelection
        )  # Disable selection of cells
        main_layout.addWidget(self.table)

        # Adjust the window width to match the table
        self.adjust_window_width()

        # Buttons layout
        button_layout = QHBoxLayout()

        # Add Wallpaper button
        self.add_button = QPushButton("Add Wallpaper")
        self.add_button.setCursor(Qt.PointingHandCursor)  # Change cursor to pointer
        self.add_button.clicked.connect(self.add_image)
        button_layout.addWidget(self.add_button)

        # Clear All button
        self.clear_button = QPushButton("Clear")
        self.clear_button.setCursor(Qt.PointingHandCursor)  # Change cursor to pointer
        self.clear_button.clicked.connect(self.clear_all)
        button_layout.addWidget(self.clear_button)

        main_layout.addLayout(button_layout)

        # Checkbox for "Hide when closed"
        self.hide_checkbox = QCheckBox(f" Hide when closed")
        self.hide_checkbox.stateChanged.connect(self.toggle_hide_on_minimize)
        self.hide_checkbox.setStyleSheet(
            """
                QCheckBox {
                    color: white;
                }
            """
        )

        # Checkbox for "Start at startup
        self.startup_checkbox = QCheckBox(f" Run at startup")
        self.startup_checkbox.stateChanged.connect(self.toggle_startup)
        self.startup_checkbox.setStyleSheet(
            """
                QCheckBox {
                    color: white;
                }
            """
        )

        # Add checkboxes to the layout
        checkbox_layout = QHBoxLayout()
        checkbox_layout.addWidget(self.hide_checkbox)
        checkbox_layout.addWidget(self.startup_checkbox)
        main_layout.addLayout(checkbox_layout)

        # Central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.load_data()  # Load data from the local storage file
        self.hide_checkbox.setChecked(self.hide_on_minimize)  # Set the checkbox state
        self.update_table()  # Populate the table with the loaded data

        # Start the scheduler
        self.start_scheduler()

        # Check if "Run at startup" is enabled and hide the window
        if self.startup_checkbox.isChecked():
            self.hide()  # Hide the main window
            self.tray_icon.show()  # Show the system tray icon

        # Debug startup behavior
        #with open("startup_debug.log", "w") as log_file:
        #    log_file.write(f"Working directory: {os.getcwd()}\n")
        #    log_file.write(f"JSON file path: {self.get_storage_file_path()}\n")
        #    log_file.write(f"Startup checkbox state: {self.startup_checkbox.isChecked()}\n")

    def on_tray_icon_activated(self, reason):
        # Handle system tray icon activation
        if reason == QSystemTrayIcon.Trigger:  # Triggered by a left-click
            self.show()

    def get_storage_file_path(self):
        # Get the absolute path of the JSON storage file.
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.json")

    def load_data(self):
        # Load data and settings from the local storage file.
        storage_file = "./schedule.json"
        if os.path.exists(storage_file):
            with open(storage_file, "r") as file:
                try:
                    data = json.load(file)
                    if isinstance(data, dict):  # Ensure the file contains a dictionary
                        self.images = data.get("images", [])  # Load images or default to an empty list
                        self.hide_on_minimize = data.get("hide_on_minimize", False)  # Default: False
                        self.startup_checkbox.setChecked(data.get("run_at_startup", False))  # Default: False
                    else:
                        # Reset to default if the file contains invalid data
                        self.images = []
                        self.hide_on_minimize = False
                except json.JSONDecodeError:
                    # Reset to default if the file is corrupted
                    self.images = []
                    self.hide_on_minimize = False
        else:
            # Initialize as empty if the file doesn't exist
            self.images = []
            self.hide_on_minimize = False

    def save_data(self):
        # Save the current data and settings to the local storage file
        storage_file = "schedule.json"
        data = {
            "images": self.images,
            "hide_on_minimize": self.hide_on_minimize,
            "run_at_startup": self.startup_checkbox.isChecked(),
        }
        with open(storage_file, "w") as file:
            json.dump(data, file, indent=4)

    def add_image(self):
        # Add a new image with a start time to the table
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Wallpaper", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            # Temporarily add the image with a placeholder start time
            current_time = datetime.now().strftime("%H:%M")  # Get the current time
            self.images.append((file_path, current_time))  # Use current time as default start time
            row = len(self.images) - 1  # Get the index of the newly added image

            # Use the existing change_time function to set the start time
            self.change_time(row)

            # Update the table and save the data
            self.update_table()
            self.save_data()

    def update_table(self):
        """Update the table with the current images and dynamically calculated time periods."""
        try:
            # Sort the images list by start time (ascending order)
            self.images.sort(key=lambda x: x[1])  # Sort by the second element (start_time)

            self.table.setRowCount(len(self.images))

            for row, (image_path, start_time) in enumerate(self.images):
                # Calculate the end time dynamically
                next_row = (row + 1) % len(self.images)  # Wrap around to the first wallpaper
                end_time = self.images[next_row][1]

                # Thumbnail widget with hover and click functionality
                thumbnail_label = ClickableLabel(
                    row=row,
                    on_click=lambda r=row: self.change_image(r),
                    is_thumbnail=True,  # Mark as a thumbnail
                )
                pixmap = QPixmap(image_path).scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumbnail_label.setPixmap(pixmap)
                thumbnail_label.setAlignment(Qt.AlignCenter)
                thumbnail_label.setCursor(Qt.PointingHandCursor)
                self.table.setCellWidget(row, 0, thumbnail_label)

                # File name column
                wallpaper_item = QTableWidgetItem(f"{os.path.basename(image_path)}")
                wallpaper_item.setTextAlignment(Qt.AlignCenter)
                wallpaper_item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(row, 1, wallpaper_item)

                # Time slot column
                time_slot_label = ClickableLabel(
                    row=row,
                    on_click=lambda r=row: self.change_time(r),
                    is_thumbnail=False,  # Mark as a time slot
                )
                time_slot_label.setText(f"{start_time}")  # Display only the start time
                time_slot_label.setAlignment(Qt.AlignCenter)
                time_slot_label.setCursor(Qt.PointingHandCursor)
                self.table.setCellWidget(row, 2, time_slot_label)

                # Remove button
                remove_button = QPushButton("X")
                remove_button.clicked.connect(lambda _, r=row: self.remove_row(r))
                remove_button.setCursor(Qt.PointingHandCursor)
                remove_button.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #333;
                        color: white;
                        border: none;
                    }
                    QPushButton:hover {
                        background-color: #555;
                    }
                    """
                )
                self.table.setCellWidget(row, 3, remove_button)

        except Exception as e:
            print(f"Error in update_table: {e}")

    def change_image(self, row):
        # Change the image for a specific row
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select New Wallpaper", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            # Update the image path while keeping the start time intact
            self.images[row] = (file_path, self.images[row][1])  # Only two elements now
            self.update_table()
            self.save_data()  # Save the updated data

    def change_time(self, row):
        # Open the time scheduler dialog to edit the start time for a specific row
        time_dialog = QDialog(self)
        time_dialog.setWindowTitle("Edit Start Time")
        time_dialog.setFixedSize(300, 150)

        parent_geometry = self.geometry()
        time_dialog.move(parent_geometry.right(), parent_geometry.top() - 31)

        layout = QVBoxLayout()
        label = QLabel("Edit start time (HH:MM):")
        layout.addWidget(label)

        time_input = QLineEdit(self.images[row][1])  # Pre-fill with the current start time
        time_input.setMaxLength(5)
        time_input.setAlignment(Qt.AlignCenter)
        time_input.setStyleSheet(
            """
            QLineEdit {
                color: white;
                background-color: #444;
                border: 1px solid #555;
                padding: 5px;
                font-size: 16px;
                text-align: center;
            }
            """
        )
        layout.addWidget(time_input)

        def enforce_time_format():
            text = time_input.text()
            if len(text) != 5 or text[2] != ":":
                time_input.setText(self.images[row][1])
                return
            hh, mm = text.split(":")
            if not (hh.isdigit() and mm.isdigit()):
                time_input.setText(self.images[row][1])

        time_input.textChanged.connect(enforce_time_format)
        time_input.keyPressEvent = lambda event: self.handle_keypress(event, time_input)

        save_button = QPushButton("Save")
        layout.addWidget(save_button)

        time_dialog.setLayout(layout)

        # Save the time only when the "Save" button is clicked
        def save_time():
            selected_time = time_input.text()

            if any(
                time_slot == selected_time
                for i, (_, time_slot) in enumerate(self.images)
                if i != row
            ):
                label.setText("Start time already in use. Choose another.")
                return

            # Update the time slot for the current row
            self.images[row] = (self.images[row][0], selected_time)
            self.update_table()
            self.save_data()
            time_dialog.accept()  # Close the dialog

        save_button.clicked.connect(save_time)

        # Execute the dialog (blocking)
        if time_dialog.exec_() != QDialog.Accepted:
            # If the dialog is rejected (e.g., "X" is clicked), remove the placeholder entry
            self.images.pop(row)

    def handle_keypress(self, event, time_input):
        # Handle keypress events for time input
        cursor_pos = time_input.cursorPosition()
        text = time_input.text()

        if event.key() in (Qt.Key_Left, Qt.Key_Right):  # Arrow key navigation
            if event.key() == Qt.Key_Left:
                if cursor_pos > 0:
                    # Prevent skipping the second digit of hours when moving left
                    time_input.setCursorPosition(
                        cursor_pos - 1 if cursor_pos != 3 else 2
                    )
            elif event.key() == Qt.Key_Right:
                if cursor_pos < 5:
                    time_input.setCursorPosition(
                        cursor_pos + 1 if cursor_pos != 2 else 4
                    )
            return

        if event.key() == Qt.Key_Backspace:  # Allow deleting numbers
            if cursor_pos > 0 and cursor_pos != 3:  # Prevent deleting the colon
                new_cursor_pos = cursor_pos - 1
                text = text[:new_cursor_pos] + "0" + text[new_cursor_pos + 1 :]
                time_input.setText(text)
                time_input.setCursorPosition(new_cursor_pos)
            return

        if event.text().isdigit():  # Allow typing numbers
            if cursor_pos < 2:  # Editing hours
                text = text[:cursor_pos] + event.text() + text[cursor_pos + 1 :]
                time_input.setText(text)
                time_input.setCursorPosition(
                    min(cursor_pos + 1, 2)
                )  # Move cursor forward
                if cursor_pos == 1:  # Jump to minutes after 2 digits
                    time_input.setCursorPosition(3)
            elif cursor_pos > 2 and cursor_pos < 5:  # Editing minutes
                text = text[:cursor_pos] + event.text() + text[cursor_pos + 1 :]
                time_input.setText(text)
                time_input.setCursorPosition(
                    min(cursor_pos + 1, 5)
                )  # Move cursor forward

        elif cursor_pos == 2:  # Prevent editing the colon
            time_input.setCursorPosition(3)

        event.accept()

    def remove_row(self, row):
        # Remove a specific row from the table and the images list
        self.images.pop(row)
        self.update_table()
        self.save_data()  # Save data after removing a row

    def clear_all(self):
        # Clear all entries from the table and reset the images list
        self.images.clear()
        self.table.setRowCount(0)
        self.save_data()  # Save data after clearing all entries

    def start_scheduler(self):
        # Immediately check wallpaper once at launch
        self.check_wallpaper_change()
        
        # Start the scheduler to change wallpapers at the specified times
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_wallpaper_change)
        self.timer.start(30000)  # Check every 30 seconds

    def check_wallpaper_change(self):
        """Check if it's time to change the wallpaper."""
        now = datetime.now().strftime("%H:%M")
        for i, (image_path, start_time) in enumerate(self.images):
            # Calculate the end time dynamically
            next_index = (i + 1) % len(self.images)  # Wrap around to the first wallpaper
            end_time = self.images[next_index][1]

            # Check if the current time is within the period
            if start_time <= now < end_time or (start_time > end_time and (now >= start_time or now < end_time)):
                set_wallpaper(image_path)
                break

    def get_dark_theme(self):
        # Return a dark theme stylesheet
        return """
        QMainWindow {
            background-color: #2b2b2b;
            color: white;
        }
        QPushButton {
            background-color: #444;
            color: white;
            border: none;
            padding: 10px;
        }
        QPushButton:hover {
            background-color: #555;
        }
        QTableWidget {
            background-color: #333;
            color: white;
            gridline-color: #444;
        }
        QHeaderView::section {
            background-color: #444;
            color: white;
            padding: 5px;
            border: none;
        }
        QLineEdit {
            background-color: #444;
            color: white;
            border: 1px solid #555;
            padding: 5px;
        }
        QLabel {
            color: white;
        }
        QDialog {
            background-color: #2b2b2b;
        }
        """

    def adjust_window_width(self):
        # Ensure the window width matches the table but prevent shrinking
        total_width = (
            self.table.columnWidth(0)
            + self.table.columnWidth(1)  # Wallpaper column
            + self.table.verticalHeader().width()  # Time Slot column
            + self.table.frameWidth() * 2  # Vertical header width  # Table frame width
        )
        self.setMinimumWidth(total_width)  # Prevent shrinking

    def toggle_hide_on_minimize(self, state):
        # Enable or disable hiding to the system tray when minimized
        self.hide_on_minimize = state == Qt.Checked
        self.save_data()  # Save the updated state

    def toggle_startup(self, state):
        # Enable or disable starting the application at system startup
        app_name = "Dayflow"
        app_path = os.path.abspath(sys.argv[0])  # Get the full path of the script

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if state == Qt.Checked:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
                    print(f"Startup enabled: {app_path}")
                else:
                    winreg.DeleteValue(key, app_name)
                    print("Startup disabled")
        except FileNotFoundError:
            print("Registry key not found")
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                "Unable to modify startup settings. Please run as administrator.",
            )
            print("Permission denied")
        except Exception as e:
            print(f"Unexpected error: {e}")

        self.save_data()  # Save the updated state

    def closeEvent(self, event):
        # Override close event to minimize to tray if enabled
        if self.force_exit:
            event.accept()  # Allow the application to close
        elif self.hide_on_minimize:
            event.ignore()
            self.hide()
            self.tray_icon.show()
        else:
            event.accept()

    def exit_application(self):
        # Handle the Exit action from the system tray."""
        self.force_exit = True  # Set the flag to allow exiting
        self.close()  # Trigger the close event

# Run the application
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BackgroundChangerApp()
    window.show()
    sys.exit(app.exec_())
