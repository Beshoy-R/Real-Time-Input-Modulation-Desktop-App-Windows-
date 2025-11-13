import sys
import os


import json
import threading
import random
import time
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSystemTrayIcon,
    QMenu,
    QTabWidget,
    QFrame,
    QToolButton,
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt, QSize
from pynput import mouse, keyboard
import string
import ctypes
import platform
import sqlite3


def send_mouse_move_win32(dx, dy):
    if platform.system() != "Windows":
        return

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

    INPUT_MOUSE = 0
    MOUSEEVENTF_MOVE = 0x0001
    extra = ctypes.c_ulong(0)
    ii_ = INPUT()
    ii_.type = INPUT_MOUSE
    ii_.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, ctypes.pointer(extra))
    ctypes.windll.user32.SendInput(1, ctypes.byref(ii_), ctypes.sizeof(ii_))


try:
    import pygetwindow as gw
except ImportError:
    gw = None
try:
    import pyautogui

    pyautogui.FAILSAFE = False
except ImportError:
    pyautogui = None


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


PROFILES_FILE = resource_path("data/profiles.json")


class InputControlAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.resize(950, 785)
        self.profiles_data = self.load_json(PROFILES_FILE)
        self.icon_cache = {}  # Cache icons for speed
        self.db_path = resource_path("settings.db")
        self.init_db()
        self.settings = self.load_settings_from_db()
        self.current_group = "A"
        self.current_profile = None
        self.modulation_enabled = False
        self.modulation_thread = None
        self.listener_thread = None
        self.stop_event = threading.Event()
        self.tray_icon = None
        self.tray_menu = None
        self.tray_enable_action = None
        self.group_a_list = None
        self.group_b_list = None
        self.init_ui()
        self.setup_tray_icon()
        self.setup_hotkey_listener()
        self.center_on_screen()

    def load_json(self, path):
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS profile_settings (
            name TEXT PRIMARY KEY,
            x REAL,
            y REAL
        )"""
        )
        conn.commit()
        conn.close()

    def load_settings_from_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT name, x, y FROM profile_settings")
        rows = c.fetchall()
        conn.close()
        settings = {}
        for name, x, y in rows:
            settings[name] = {"x": x, "y": y}
        return settings

    def save_setting_to_db(self, name, x, y):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO profile_settings (name, x, y) VALUES (?, ?, ?)""",
            (name, x, y),
        )
        conn.commit()
        conn.close()
        self.settings[name] = {"x": x, "y": y}

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 10)  # Remove margins except bottom

        title_bar = QFrame()
        title_bar.setStyleSheet("background: #0f1011;")
        title_bar.setFixedHeight(36)
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(8, 4, 8, 4)

        app_icon_label = QLabel()
        app_icon = QIcon(resource_path("icons/logo.png"))
        app_icon_label.setPixmap(app_icon.pixmap(24, 24))
        title_bar_layout.addWidget(app_icon_label)

        app_title = QLabel("Input Control Assistant")
        app_title.setStyleSheet("color: #ff2d55; font-weight: bold; font-size: 14px;")
        title_bar_layout.addWidget(app_title)

        title_bar_layout.addStretch()

        min_button = QToolButton()
        min_icon = QIcon(resource_path("icons/min_icon.png"))
        min_button.setIcon(min_icon)
        min_button.setStyleSheet(
            """
            QToolButton {
                color: #a259f7;
                background: transparent;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QToolButton:hover {
                color: #fff;
                background: #a259f7;
            }
        """
        )
        min_button.setFixedSize(36, 28)
        min_button.clicked.connect(self.showMinimized)

        max_button = QToolButton()
        max_icon = QIcon(resource_path("icons/max_icon.png"))
        max_button.setIcon(max_icon)
        max_button.setStyleSheet(
            """
            QToolButton {
                color: #a259f7;
                background: transparent;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QToolButton:hover {
                color: #fff;
                background: #a259f7;
            }
        """
        )
        max_button.setFixedSize(36, 28)
        max_button.clicked.connect(self.toggle_maximize)

        close_button = QToolButton()
        close_icon = QIcon(resource_path("icons/close_icon.png"))
        close_button.setIcon(close_icon)
        close_button.setStyleSheet(
            """
            QToolButton {
                color: #a259f7;
                background: transparent;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QToolButton:hover {
                color: #fff;
                background: #ff2d55;
            }
        """
        )
        close_button.setFixedSize(36, 28)
        close_button.clicked.connect(self.close)

        title_bar_layout.addWidget(min_button)
        title_bar_layout.addWidget(max_button)
        title_bar_layout.addWidget(close_button)

        layout.addWidget(title_bar)

        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(10, 10, 10, 0)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.tabBar().setDocumentMode(True)
        self.tabs.tabBar().setExpanding(True) 

        tab_style = """
            QTabBar::tab:first {
                margin-left: 35%;
            }
            QTabBar::tab:last {
                margin-right: 35%;
            }
        """
        self.tabs.setStyleSheet(tab_style)

        self.group_a_tab = QWidget()
        self.group_b_tab = QWidget()
        self.tabs.addTab(self.group_a_tab, "Profile 1")
        self.tabs.addTab(self.group_b_tab, "Profile 2")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tabs)

        self.active_profile_widget = QWidget()
        active_profile_layout = QHBoxLayout()
        active_profile_layout.setContentsMargins(0, 0, 0, 0)
        active_profile_layout.setSpacing(8)
        self.active_profile_icon = QLabel()
        self.active_profile_icon.setFixedSize(48, 48)
        self.active_profile_name = QLabel("No profile selected")
        self.active_profile_name.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #a259f7;"
        )
        active_profile_layout.addWidget(self.active_profile_icon)
        active_profile_layout.addWidget(self.active_profile_name)
        self.active_profile_widget.setLayout(active_profile_layout)
        content_layout.addWidget(self.active_profile_widget, alignment=Qt.AlignHCenter)

        self.config_widget = QWidget()
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("X-Axis:"))
        self.x_input = QLineEdit()
        self.x_input.setPlaceholderText("e.g. 0.0")
        self.x_input.setStyleSheet(
            "background: #181a1b; color: #ff2d55; border: 1px solid #a259f7; font-weight: bold;"
        )
        config_layout.addWidget(self.x_input)
        config_layout.addWidget(QLabel("Y-Axis:"))
        self.y_input = QLineEdit()
        self.y_input.setPlaceholderText("e.g. 15.0")
        self.y_input.setStyleSheet(
            "background: #181a1b; color: #ff2d55; border: 1px solid #a259f7; font-weight: bold;"
        )
        config_layout.addWidget(self.y_input)
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(
            "background: #a259f7; color: #fff; font-weight: bold; border-radius: 6px; padding: 4px 16px;"
        )
        self.save_btn.clicked.connect(self.save_settings)
        config_layout.addWidget(self.save_btn)
        self.config_widget.setLayout(config_layout)
        content_layout.addWidget(self.config_widget)

        self.group_a_list = self.create_profile_list("A")
        self.group_b_list = self.create_profile_list("B")
        group_a_layout = QVBoxLayout(self.group_a_tab)
        group_a_layout.setContentsMargins(10, 10, 10, 10)
        group_a_layout.setSpacing(10)
        group_a_layout.addWidget(self.group_a_list)
        group_b_layout = QVBoxLayout(self.group_b_tab)
        group_b_layout.setContentsMargins(10, 10, 10, 10)
        group_b_layout.setSpacing(10)
        group_b_layout.addWidget(self.group_b_list)

        content_layout.addWidget(self.tabs)

        QApplication.instance().processEvents()  # Process pending events to ensure widgets have proper sizes
        self.update_profile_grid_layout()

        self.enable_btn = QPushButton("Enable Input Modulation")
        self.enable_btn.setCheckable(True)
        self.enable_btn.clicked.connect(self.toggle_modulation)
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setStyleSheet(
            "background: #ff2d55; color: #fff; font-weight: bold; border-radius: 6px; padding: 4px 16px;"
        )
        self.restart_btn.clicked.connect(self.restart_software)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.enable_btn)
        btn_row.addWidget(self.restart_btn)
        content_layout.addLayout(btn_row)
        about_label = QLabel(
            "<b>Developed by: <span style='color:#ff2d55;'>Besho Riad</span></b><br>"
        )
        about_label.setAlignment(Qt.AlignHCenter)
        about_label.setStyleSheet("margin-top: 16px; margin-bottom: 8px;")
        content_layout.addWidget(about_label)

        layout.addWidget(content_area)

        self.setLayout(layout)
        self.apply_theme()
        self.randomize_window_title()

    def on_tab_changed(self, index):
        if index == 0:
            self.current_group = "A"
        else:
            self.current_group = "B"
        current_list = self.get_current_profile_list()
        current_item = current_list.currentItem() if current_list else None
        self.on_profile_selected(current_item, None)

    def on_profile_selected(self, current, previous):
        if current:
            self.current_profile = current.text()
            self.update_config_fields(current)
            profile_data = self.get_profile_data(self.current_profile)
            icon_path = profile_data.get("icon", "")
            full_icon_path = os.path.join(os.path.dirname(__file__), icon_path)
            if os.path.exists(full_icon_path):
                self.active_profile_icon.setPixmap(QIcon(full_icon_path).pixmap(48, 48))
            else:
                self.active_profile_icon.clear()
            self.active_profile_name.setText(self.current_profile)
        else:
            self.active_profile_icon.clear()
            self.active_profile_name.setText("No profile selected")
            self.x_input.clear()
            self.y_input.clear()

    def update_config_fields(self, item):
        if not item:
            self.x_input.clear()
            self.y_input.clear()
            return
        name = item.text()
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT x, y FROM profile_settings WHERE name=?", (name,))
        row = c.fetchone()
        conn.close()
        if row:
            x_val, y_val = row
        else:
            profile_data = self.get_profile_data(name)
            x_val = profile_data.get("x", "")
            y_val = profile_data.get("y", "")
        self.x_input.setText(str(x_val))
        self.y_input.setText(str(y_val))

    def save_settings(self):
        profile_list = self.get_current_profile_list()
        item = profile_list.currentItem() if profile_list else None
        if not item:
            return
        name = item.text()
        try:
            x = float(self.x_input.text())
            y = float(self.y_input.text())
        except ValueError:
            return
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO profile_settings (name, x, y) VALUES (?, ?, ?)""",
            (name, x, y),
        )
        conn.commit()
        conn.close()
        self.settings[name] = {"x": x, "y": y}

    def get_current_profile_item(self):
        profile_list = self.get_current_profile_list()
        if not profile_list:
            return None
        return profile_list.currentItem()

    def get_current_profile_list(self):
        return self.group_a_list if self.current_group == "A" else self.group_b_list

    def get_profile_data(self, profile_name):
        """Get profile data from the loaded profiles."""
        for profile in self.profiles_data.get("profiles", []):
            if profile.get("name") == profile_name:
                return profile
        return {}

    def get_current_profile_xy(self):
        item = self.get_current_profile_item()
        name = item.text() if item else None
        x = float(self.x_input.text()) if self.x_input.text() else 0.0
        y = float(self.y_input.text()) if self.y_input.text() else 0.0
        return x, y

    def setup_tray_icon(self):
        icon_path = resource_path("icons/logo.png")
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray_menu = QMenu()
        show_action = QAction("Show/Hide", self)
        show_action.triggered.connect(self.toggle_window_visibility)
        self.tray_enable_action = QAction("Enable Modulation (F8)", self)
        self.tray_enable_action.setCheckable(True)
        self.tray_enable_action.setChecked(self.modulation_enabled)
        self.tray_enable_action.triggered.connect(self.toggle_modulation)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(self.tray_enable_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_window_visibility()

    def closeEvent(self, event):
        event.accept()
        QApplication.quit()

    def setup_hotkey_listener(self):
        def on_press(key):
            try:
                if key == keyboard.Key.f8:
                    self.toggle_modulation()
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    def toggle_modulation(self):
        self.modulation_enabled = not self.modulation_enabled
        self.enable_btn.setChecked(self.modulation_enabled)
        if self.tray_enable_action:
            self.tray_enable_action.setChecked(self.modulation_enabled)
            self.tray_enable_action.setText(
                "Disable Modulation (F8)"
                if self.modulation_enabled
                else "Enable Modulation (F8)"
            )
        if self.modulation_enabled:
            delay = random.uniform(0.5, 2.0)
            threading.Thread(
                target=self._delayed_start_modulation, args=(delay,), daemon=True
            ).start()
        else:
            delay = random.uniform(0.5, 2.0)
            threading.Thread(
                target=self._delayed_stop_modulation, args=(delay,), daemon=True
            ).start()

    def _delayed_start_modulation(self, delay):
        time.sleep(delay)
        if self.modulation_enabled:
            self.stop_event.clear()
            self.modulation_thread = threading.Thread(
                target=self.modulation_loop, daemon=True
            )
            self.modulation_thread.start()

    def _delayed_stop_modulation(self, delay):
        time.sleep(delay)
        self.stop_event.set()

    def modulation_loop(self):
        mouse_controller = mouse.Controller()
        keyboard_controller = keyboard.Controller()
        rest_timer = 0
        rest_interval = random.uniform(3, 7)
        while not self.stop_event.is_set():
            if self.modulation_enabled and self.get_current_profile_item():
                if self.is_left_mouse_held():
                    x, y = self.get_current_profile_xy()
                    interval = random.uniform(0.010, 0.040)
                    if random.random() < 0.03:
                        mistake_x = random.uniform(-2, 2)
                        mistake_y = random.uniform(-2, 2)
                        moved = False
                        try:
                            send_mouse_move_win32(int(mistake_x), int(mistake_y))
                            moved = True
                        except Exception:
                            pass
                        if not moved and pyautogui:
                            try:
                                pyautogui.moveRel(mistake_x, mistake_y)
                                moved = True
                            except Exception:
                                pass
                        if not moved:
                            mouse_controller.move(mistake_x, mistake_y)
                    jitter_x = x + random.uniform(-1.5, 1.5)
                    jitter_y = y + random.uniform(-1.5, 1.5)
                    moved = False
                    try:
                        send_mouse_move_win32(int(jitter_x), int(jitter_y))
                        moved = True
                    except Exception:
                        pass
                    if not moved and pyautogui:
                        try:
                            pyautogui.moveRel(jitter_x, jitter_y)
                            moved = True
                        except Exception:
                            pass
                    if not moved:
                        mouse_controller.move(jitter_x, jitter_y)
                    rest_timer += interval
                    if rest_timer > rest_interval:
                        time.sleep(random.uniform(0.1, 0.3))
                        rest_timer = 0
                        rest_interval = random.uniform(3, 7)
                    else:
                        time.sleep(interval)
                else:
                    time.sleep(0.01)
            else:
                time.sleep(0.05)

    def is_left_mouse_held(self):
        if not hasattr(self, "_mouse_pressed"):
            self._mouse_pressed = False

            def on_click(x, y, button, pressed):
                if button == mouse.Button.left:
                    self._mouse_pressed = pressed

            self._mouse_listener = mouse.Listener(on_click=on_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
        return getattr(self, "_mouse_pressed", False)

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_profile_grid_layout()

    def update_profile_grid_layout(self):
        if self.group_a_tab.width() <= 0:
            return  

        available_width = (
            self.group_a_tab.width() - 30
        )  
        item_width = 80  # Base size
        spacing = 10

        items_per_row = max(1, available_width // (item_width + spacing))

        new_item_width = (
            available_width - (items_per_row - 1) * spacing
        ) // items_per_row

        if self.group_a_list:
            self.group_a_list.setGridSize(QSize(new_item_width, 90))
        if self.group_b_list:
            self.group_b_list.setGridSize(QSize(new_item_width, 90))

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton and event.position().y() < 36
        ):  
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "drag_position"):
            if event.position().y() < 36:  # Only move if dragging from title bar
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def apply_theme(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #181a1b;
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: 2px solid #a259f7;
                border-radius: 12px;
                background: #181a1b;
                margin: 8px;
            }
            
            /* Custom tab alignment handled through direct styling */
            QTabBar::tab {
                background: #23272b;
                color: #a259f7;
                border: 1.5px solid #a259f7;
                border-radius: 8px 8px 0 0;
                padding: 8px 24px;
                font-weight: bold;
                margin: 2px;
                min-width: 160px;
                max-width: 200px;
                font-size: 16px;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background: #a259f7;
                color: #fff;
                border: 2.5px solid #ff2d55;
            }
            QPushButton {
                background: #23272b;
                color: #ff2d55;
                border: 1.5px solid #a259f7;
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: bold;
                margin: 2px;
                height: 30px;
                font-size: 15px;
            }
            QPushButton:hover {
                background: #a259f7;
                color: #fff;
                border: 2.5px solid #ff2d55;
            }
            QPushButton:checked {
                background: #ff2d55;
                color: #fff;
                border: 2.5px solid #a259f7;
            }
            QLabel {
                color: #ff2d55;
                font-weight: bold;
            }
            QLineEdit {
                background: #181a1b;
                color: #ff2d55;
                border: 1.5px solid #a259f7;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 15px;
                margin: 2px;
            }
            QLineEdit:focus {
                border: 2.5px solid #ff2d55;
                background: #23272b;
                color: #fff;
            }
            QListWidget {
                background: #23272b;
                border: 2px solid #a259f7;
                border-radius: 12px;
                padding: 8px;
                font-size: 15px;
                color: #ff2d55;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                color: #ff2d55;
                font-weight: bold;
                border-radius: 8px;
                margin: 4px;
                padding: -2px 12px;
            }
            QListWidget::item:selected, QListWidget::item:hover {
                background: #a259f7;
                color: #fff;
                
            }
            /* Active profile display */
            QWidget#active_profile_widget {
                border-radius: 16px;
                margin: 12px 0 18px 0;
                padding: 10px 24px;
                height: 40px;
                background: #23272b;
            }
            QLabel#active_profile_name {
                color: #fff;
                font-size: 22px;
                font-weight: bold;
                letter-spacing: 1px;
            }
        """
        )
        self.active_profile_widget.setObjectName("active_profile_widget")
        self.active_profile_name.setObjectName("active_profile_name")

    def randomize_window_title(self):
        rand_title = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        self.setWindowTitle(rand_title)
        try:
            if sys.platform == "win32":
                new_name = (
                    "".join(random.choices(string.ascii_letters + string.digits, k=10))
                    + ".exe"
                )
                ctypes.windll.kernel32.SetConsoleTitleW(new_name)
        except Exception:
            pass

    def restart_software(self):
        import subprocess
        import os

        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        rand_arg = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        subprocess.Popen([python, script, rand_arg])
        QApplication.quit()

    def create_profile_list(self, group):
        profile_list = QListWidget()
        profile_list.setViewMode(QListWidget.IconMode)
        profile_list.setIconSize(QSize(64, 64))
        profile_list.setGridSize(QSize(80, 90))
        profile_list.setResizeMode(QListWidget.Adjust)
        profile_list.setMovement(QListWidget.Static)
        profile_list.setSpacing(10)
        profile_list.setUniformItemSizes(True)
        profile_list.setWordWrap(True)
        profile_list.setFlow(QListWidget.LeftToRight)
        profile_list.setResizeMode(QListWidget.Adjust)
        profile_list.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        profile_list.setStyleSheet(
            "background: #23272b; color: #ff2d55; font-weight: bold; border: none;"
        )

        profiles_list = self.profiles_data.get("profiles", [])
        for profile_data in profiles_list:
            if profile_data.get("group") == group:
                name = profile_data.get("name", "")
                
                if name in self.icon_cache:
                    icon = self.icon_cache[name]
                else:
                    icon_path = profile_data.get("icon", "")
                    full_icon_path = os.path.join(os.path.dirname(__file__), icon_path)
                    icon = (
                        QIcon(full_icon_path)
                        if os.path.exists(full_icon_path)
                        else QIcon()
                    )
                    self.icon_cache[name] = icon
                item = QListWidgetItem(icon, name)
                item.setTextAlignment(Qt.AlignHCenter)
                profile_list.addItem(item)
        profile_list.currentItemChanged.connect(self.on_profile_selected)
        return profile_list


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = InputControlAssistant()
    window.show()
    sys.exit(app.exec())
