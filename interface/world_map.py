import sys
import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, Slot, QPropertyAnimation, 
    QEasingCurve, QPointF, QRectF
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, 
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsObject,
    QDockWidget, QWidget, QVBoxLayout, QLabel, QTextEdit
)

import win32gui
import pywinauto
import websocket

# Scale factor to fit monitors on screen
SCALE = 0.25

ROOT_DIR = Path(__file__).resolve().parents[1]
AUDIT_LOG_FILE = ROOT_DIR / "logs" / "audit" / "turns.jsonl"


class AvatarMarker(QGraphicsObject):
    def __init__(self):
        super().__init__()
        self.setZValue(100)

    def boundingRect(self):
        return QRectF(-10, -10, 20, 20)

    def paint(self, painter, option, widget=None):
        painter.setBrush(QBrush(QColor(0, 255, 0)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.boundingRect())


class WSClientThread(QThread):
    persona_update = Signal(dict)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.ws = None
        self.running = True

    def run(self):
        while self.running:
            try:
                self.ws = websocket.WebSocket()
                self.ws.connect(self.url)
                while self.running:
                    msg = self.ws.recv()
                    if msg:
                        data = json.loads(msg)
                        self.persona_update.emit(data)
            except Exception as e:
                time.sleep(2)  # reconnect delay

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()


class MapGraphicsView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self._is_panning = False
        self._pan_start = None

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            # Adjust scrollbars
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)


class WorldMapWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gopher-bot World Map")
        self.resize(1000, 700)

        # Canvas
        self.scene = QGraphicsScene()
        self.view = MapGraphicsView(self.scene)
        self.setCentralWidget(self.view)

        # Sidebar panels
        self._init_sidebar()

        # Canvas elements
        self.monitor_items = []
        self.window_items = {}
        
        # Avatar Marker
        self.avatar_marker = AvatarMarker()
        self.scene.addItem(self.avatar_marker)
        
        # Animation
        self.avatar_anim = QPropertyAnimation(self.avatar_marker, b"pos")
        self.avatar_anim.setDuration(300)
        self.avatar_anim.setEasingCurve(QEasingCurve.InOutQuad)

        self.draw_monitors()

        # Timers
        self.window_timer = QTimer()
        self.window_timer.timeout.connect(self.refresh_windows)
        self.window_timer.start(2000)

        self.audit_timer = QTimer()
        self.audit_timer.timeout.connect(self.refresh_audit)
        self.audit_timer.start(5000)

        # WebSocket
        self.ws_thread = WSClientThread("ws://localhost:5000/avatar-ws")
        self.ws_thread.persona_update.connect(self.on_persona_update)
        self.ws_thread.start()
        
        # Initial draw
        self.refresh_windows()

    def _init_sidebar(self):
        dock = QDockWidget("Dashboard", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        container = QWidget()
        layout = QVBoxLayout(container)

        # State Panel
        self.lbl_state = QLabel("State: Unknown")
        self.lbl_coord = QLabel("Coordinator: None")
        self.lbl_focus = QLabel("Focus: None")
        self.lbl_neuro = QLabel("DA: - | NE: - | 5HT: - | ACh: -")
        
        layout.addWidget(self.lbl_state)
        layout.addWidget(self.lbl_coord)
        layout.addWidget(self.lbl_focus)
        layout.addWidget(self.lbl_neuro)
        
        layout.addSpacing(20)
        layout.addWidget(QLabel("Audit Log (Last 20 turns):"))
        
        # Audit Panel
        self.txt_audit = QTextEdit()
        self.txt_audit.setReadOnly(True)
        self.txt_audit.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_audit)

        dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def draw_monitors(self):
        for item in self.monitor_items:
            self.scene.removeItem(item)
        self.monitor_items.clear()

        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            x = geom.x() * SCALE
            y = geom.y() * SCALE
            w = geom.width() * SCALE
            h = geom.height() * SCALE

            rect = QGraphicsRectItem(x, y, w, h)
            rect.setBrush(QBrush(QColor(30, 30, 40)))
            rect.setPen(QPen(QColor(100, 100, 150), 2))
            rect.setZValue(-10)
            self.scene.addItem(rect)
            self.monitor_items.append(rect)

            text = QGraphicsTextItem(f"Monitor {i+1}\n{geom.width()}x{geom.height()}")
            text.setDefaultTextColor(QColor(150, 150, 200))
            text.setPos(x + 10, y + 10)
            text.setZValue(-9)
            self.scene.addItem(text)
            self.monitor_items.append(text)

    @Slot()
    def refresh_windows(self):
        def win_enum_handler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w >= 100 and h >= 100:
                    ctx.append((hwnd, win32gui.GetWindowText(hwnd), rect))

        windows = []
        win32gui.EnumWindows(win_enum_handler, windows)

        # Clear old items — pop each entry and remove only the two QGraphicsItems.
        # Using try/except per item because Qt may warn about scene mismatches when
        # a previous refresh partially failed, and we don't want one bad item to
        # block removal of the rest.
        old_entries = list(self.window_items.values())
        self.window_items.clear()
        for entry in old_entries:
            try:
                self.scene.removeItem(entry[0])   # rect_item
            except Exception:
                pass
            try:
                self.scene.removeItem(entry[1])   # text_item
            except Exception:
                pass

        # Draw new windows
        for hwnd, title, rect in windows:
            x = rect[0] * SCALE
            y = rect[1] * SCALE
            w = (rect[2] - rect[0]) * SCALE
            h = (rect[3] - rect[1]) * SCALE

            rect_item = QGraphicsRectItem(x, y, w, h)
            rect_item.setBrush(QBrush(QColor(50, 50, 70, 200)))
            rect_item.setPen(QPen(QColor(200, 200, 250), 1))
            rect_item.setZValue(0)
            self.scene.addItem(rect_item)

            text_item = QGraphicsTextItem(title)
            text_item.setDefaultTextColor(QColor(255, 255, 255))
            text_item.setPos(x + 5, y + 5)
            text_item.setZValue(1)
            
            # Simple text clipping
            font_metric = text_item.font()
            # We don't strictly clip in this stub, but we could.
            
            self.scene.addItem(text_item)
            self.window_items[title] = (rect_item, text_item, (x, y, w, h))

    @Slot()
    def refresh_audit(self):
        if not AUDIT_LOG_FILE.exists():
            return
        
        try:
            with open(AUDIT_LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            recent = lines[-20:]
            display_text = ""
            for line in recent:
                try:
                    data = json.loads(line)
                    display_text += f"[{data.get('timestamp', '')}] {data.get('action', '')}\n"
                except:
                    display_text += line
            
            self.txt_audit.setText(display_text)
        except Exception as e:
            self.txt_audit.setText(f"Error reading audit log: {e}")

    @Slot(dict)
    def on_persona_update(self, payload):
        state = payload.get("state", "Unknown")
        coord = payload.get("coordinator", "None")
        focus = payload.get("focus_window", "None")
        neuro = payload.get("neuromodulators", {})
        
        self.lbl_state.setText(f"State: {state}")
        self.lbl_coord.setText(f"Coordinator: {coord}")
        self.lbl_focus.setText(f"Focus: {focus}")
        
        da = neuro.get("da", 0.0)
        ne = neuro.get("ne", 0.0)
        serotonin = neuro.get("serotonin", 0.0)
        ach = neuro.get("ach", 0.0)
        self.lbl_neuro.setText(f"DA: {da:.2f} | NE: {ne:.2f} | 5HT: {serotonin:.2f} | ACh: {ach:.2f}")

        # Animate avatar to window
        if focus in self.window_items:
            rect_data = self.window_items[focus][2]
            # Center of the window
            target_x = rect_data[0] + rect_data[2] / 2
            target_y = rect_data[1] + rect_data[3] / 2
            
            self.avatar_anim.setStartValue(self.avatar_marker.pos())
            # pos() is relative to origin, we set translation
            self.avatar_anim.setEndValue(QPointF(target_x, target_y))
            self.avatar_anim.start()

    def closeEvent(self, event):
        self.ws_thread.stop()
        self.ws_thread.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WorldMapWindow()
    window.show()
    sys.exit(app.exec())
