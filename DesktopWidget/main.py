"""
SCD4x CO2センサー デスクトップウィジェット
HIDデバイスからCO2、温度、湿度の値を読み取り、デスクトップに表示します。
"""

import sys
import hid
import struct
import threading
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QPalette

# RP2040のVID/PID
VID = 0x2E8A
PID = 0x000A

class SensorData(QObject):
    """センサーデータを保持し、更新を通知するクラス"""
    data_updated = pyqtSignal(int, float, float)
    
    def __init__(self):
        super().__init__()
        self.co2 = 0
        self.temperature = 0.0
        self.humidity = 0.0
        self.connected = False

class HIDReader(threading.Thread):
    """バックグラウンドでHIDデバイスからデータを読み取るスレッド"""
    
    def __init__(self, sensor_data):
        super().__init__(daemon=True)
        self.sensor_data = sensor_data
        self.running = True
        self.device = None
        
    def run(self):
        """HIDデバイスに接続してデータを読み取る"""
        try:
            # デバイスを開く
            devices = hid.enumerate(VID, PID)
            target_device = None
            
            for device in devices:
                if device['usage_page'] == 0xFF00:
                    target_device = device
                    break
            
            if not target_device and devices:
                target_device = devices[0]
            
            if not target_device:
                print("HIDデバイスが見つかりません")
                return
            
            self.device = hid.device()
            self.device.open_path(target_device['path'])
            self.device.set_nonblocking(False)
            self.sensor_data.connected = True
            
            print(f"接続しました: {target_device.get('product_string', 'Unknown')}")
            
            while self.running:
                # HIDレポートを読み取り (タイムアウト1秒)
                data = self.device.read(64, timeout_ms=1000)
                
                if data and len(data) >= 6:
                    # リトルエンディアンで解析
                    co2 = struct.unpack('<H', bytes(data[0:2]))[0]
                    temp_raw = struct.unpack('<h', bytes(data[2:4]))[0]
                    hum_raw = struct.unpack('<H', bytes(data[4:6]))[0]
                    
                    temp = temp_raw / 100.0
                    hum = hum_raw / 100.0
                    
                    # データを更新して通知
                    self.sensor_data.co2 = co2
                    self.sensor_data.temperature = temp
                    self.sensor_data.humidity = hum
                    self.sensor_data.data_updated.emit(co2, temp, hum)
                    
        except Exception as e:
            print(f"HIDエラー: {e}")
            self.sensor_data.connected = False
        finally:
            if self.device:
                try:
                    self.device.close()
                except:
                    pass
    
    def stop(self):
        """スレッドを停止"""
        self.running = False

class CO2Widget(QWidget):
    """CO2センサーデータを表示するウィジェット"""
    
    def __init__(self):
        super().__init__()
        self.sensor_data = SensorData()
        self.hid_reader = None
        self.init_ui()
        self.start_reading()
        
    def init_ui(self):
        """UIを初期化"""
        self.setWindowTitle("CO2モニター")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # レイアウト
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # 背景パネル
        self.panel = QWidget()
        self.panel.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 220);
                border-radius: 15px;
            }
        """)
        
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(20, 15, 20, 15)
        panel_layout.setSpacing(8)
        
        # タイトルバー（タイトル＋閉じるボタン）
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("CO2センサー")
        title_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        close_button = QPushButton("×")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 80, 80, 180);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: rgba(255, 100, 100, 220);
            }
            QPushButton:pressed {
                background-color: rgba(200, 60, 60, 220);
            }
        """)
        close_button.setFixedSize(20, 20)
        close_button.clicked.connect(self.close)
        
        title_bar.addWidget(title_label)
        title_bar.addStretch()
        title_bar.addWidget(close_button)
        
        panel_layout.addLayout(title_bar)
        
        # CO2表示
        self.co2_label = QLabel("-- ppm")
        self.co2_label.setStyleSheet("color: #4CAF50; font-size: 32px; font-weight: bold;")
        self.co2_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.co2_label)
        
        # 温度表示
        self.temp_label = QLabel("温度: -- °C")
        self.temp_label.setStyleSheet("color: #FF9800; font-size: 16px;")
        self.temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.temp_label)
        
        # 湿度表示
        self.humidity_label = QLabel("湿度: -- %")
        self.humidity_label.setStyleSheet("color: #2196F3; font-size: 16px;")
        self.humidity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.humidity_label)
        
        # 接続状態
        self.status_label = QLabel("接続中...")
        self.status_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.status_label)
        
        self.panel.setLayout(panel_layout)
        layout.addWidget(self.panel)
        self.setLayout(layout)
        
        # ウィンドウサイズ
        self.setFixedSize(250, 220)
        
        # 画面右下に配置
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 20, screen.height() - self.height() - 60)
        
        # ドラッグ可能にする
        self.dragging = False
        self.offset = None
        
    def start_reading(self):
        """HIDデバイスからの読み取りを開始"""
        # データ更新シグナルを接続
        self.sensor_data.data_updated.connect(self.update_display)
        
        # HIDリーダースレッドを開始
        self.hid_reader = HIDReader(self.sensor_data)
        self.hid_reader.start()
        
        # 接続状態チェック用タイマー
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_connection)
        self.status_timer.start(1000)
        
    def update_display(self, co2, temp, hum):
        """表示を更新"""
        # CO2の色を値に応じて変更
        if co2 < 800:
            color = "#4CAF50"  # 緑 - 良好
        elif co2 < 1000:
            color = "#FF9800"  # オレンジ - 注意
        else:
            color = "#F44336"  # 赤 - 警告
        
        self.co2_label.setText(f"{co2} ppm")
        self.co2_label.setStyleSheet(f"color: {color}; font-size: 32px; font-weight: bold;")
        
        self.temp_label.setText(f"温度: {temp:.1f} °C")
        self.humidity_label.setText(f"湿度: {hum:.1f} %")
        
    def check_connection(self):
        """接続状態を確認"""
        if self.sensor_data.connected:
            self.status_label.setText("接続済み")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        else:
            self.status_label.setText("未接続")
            self.status_label.setStyleSheet("color: #F44336; font-size: 11px;")
    
    def mousePressEvent(self, event):
        """マウスボタン押下時"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.offset = event.pos()
    
    def mouseMoveEvent(self, event):
        """マウス移動時"""
        if self.dragging and self.offset:
            self.move(self.mapToParent(event.pos() - self.offset))
    
    def mouseReleaseEvent(self, event):
        """マウスボタン解放時"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
    
    def mouseDoubleClickEvent(self, event):
        """ダブルクリックで終了"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()
    
    def closeEvent(self, event):
        """ウィンドウクローズ時"""
        if self.hid_reader:
            self.hid_reader.stop()
            self.hid_reader.join(timeout=2)
        event.accept()
        QApplication.quit()

def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    
    # HIDライブラリの確認
    try:
        hid.enumerate()
    except Exception as e:
        print(f"HIDライブラリエラー: {e}")
        print("hidapiをインストールしてください: pip install hidapi")
        return
    
    widget = CO2Widget()
    widget.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
