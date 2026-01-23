#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
91160 智慧分诊助手 - PySide6 企业级 Mac 风格 GUI
"""
import sys
import os
import json
import asyncio
import threading
import html
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit, QFrame,
    QDialog, QScrollArea, QSplitter, QGraphicsDropShadowEffect,
    QSizePolicy, QSpacerItem, QDateEdit
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QDate, QSize, QTimer, QLocale, QSignalBlocker
from PySide6.QtGui import QFont, QColor, QPixmap, QIcon, QPalette

# 导入核心逻辑
from core.client import HealthClient
from core.qr_login import run_qr_login

# ═══════════════════════════════════════════════════════════════════════════════
# Mac 风格样式表
# ═══════════════════════════════════════════════════════════════════════════════

MAC_STYLE = """
/* 全局样式 */
QMainWindow {
    background-color: #F5F5F7;
}

QWidget {
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 14px;
    color: #1D1D1F;
}

/* 卡片样式 */
QFrame#card {
    background-color: white;
    border-radius: 12px;
    border: 1px solid rgba(0, 0, 0, 0.06);
}

/* 标题标签 */
QLabel#title {
    font-size: 22px;
    font-weight: 600;
    color: #1D1D1F;
    padding: 0;
    background: transparent;
}

QLabel#sectionTitle {
    font-size: 13px;
    font-weight: 600;
    color: #86868B;
    letter-spacing: 0.5px;
    background: transparent;
    padding: 0;
}

QLabel#fieldLabel {
    font-size: 13px;
    color: #1D1D1F;
    background: transparent;
    padding: 0;
    margin-bottom: 4px;
}

/* 下拉框 Mac 风格 */
QComboBox {
    background-color: white;
    border: 1px solid #D2D2D7;
    border-radius: 8px;
    padding: 10px 14px;
    min-height: 20px;
    font-size: 14px;
    selection-background-color: #007AFF;
}

QComboBox:hover {
    border-color: #007AFF;
}

QComboBox:focus {
    border: 2px solid #007AFF;
    padding: 9px 13px;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #86868B;
    margin-right: 10px;
}

QComboBox QAbstractItemView {
    background-color: white;
    border: 1px solid #D2D2D7;
    border-radius: 8px;
    selection-background-color: #007AFF;
    selection-color: white;
    padding: 4px;
    outline: none;
}

QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: 4px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #F0F0F5;
}

/* 日期编辑器 */
QDateEdit {
    background-color: white;
    border: 1px solid #D2D2D7;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
}

QDateEdit:focus {
    border: 2px solid #007AFF;
    padding: 9px 13px;
}

QDateEdit::drop-down {
    border: none;
    width: 30px;
}

QDateEdit::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #86868B;
    margin-right: 10px;
}

/* 主按钮 - 蓝色渐变 */
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #007AFF, stop:1 #0066D6);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 14px 28px;
    font-size: 16px;
    font-weight: 600;
}

QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0066D6, stop:1 #0055B3);
}

QPushButton#primary:pressed {
    background: #004999;
}

QPushButton#primary:disabled {
    background: #B4B4B4;
}

/* 危险按钮 - 红色 */
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF3B30, stop:1 #D63029);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 14px 28px;
    font-size: 16px;
    font-weight: 600;
}

QPushButton#danger:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D63029, stop:1 #B52620);
}

/* 次要按钮 */
QPushButton#secondary {
    background-color: #E8E8ED;
    color: #1D1D1F;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
}

QPushButton#secondary:hover {
    background-color: #DCDCE0;
}

QPushButton#secondary:pressed {
    background-color: #C8C8CC;
}

/* 日志区域 - 深色终端风格 */
QTextEdit#logViewer {
    background-color: #1D1D1F;
    color: #00D26A;
    border: none;
    border-radius: 10px;
    padding: 16px;
    font-family: "Cascadia Code", "Consolas", "SF Mono", monospace;
    font-size: 13px;
    selection-background-color: #3A3A3C;
}

/* 滚动条样式 */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 0;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.3);
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.5);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* 对话框样式 */
QDialog {
    background-color: white;
    border-radius: 12px;
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 信号通信类
# ═══════════════════════════════════════════════════════════════════════════════

class WorkerSignals(QObject):
    """后台线程与 UI 通信的信号"""
    log = Signal(str, str)  # message, color
    hospitals_loaded = Signal(list)
    deps_loaded = Signal(list)
    doctors_loaded = Signal(list)
    members_loaded = Signal(list)
    login_status = Signal(bool)
    qr_image = Signal(bytes)
    qr_status = Signal(str)
    qr_close = Signal()
    grab_finished = Signal(bool, str)
    update_button = Signal(str, str)  # text, object_name


# ═══════════════════════════════════════════════════════════════════════════════
# 二维码登录对话框
# ═══════════════════════════════════════════════════════════════════════════════

class QRLoginDialog(QDialog):
    """Mac 风格二维码登录弹窗"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫码登录")
        self.setFixedSize(380, 460)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        self.cancel_event = None
        self.login_task = None
        
        self._build_ui()
    
    def _build_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel#dialogTitle {
                font-size: 20px;
                font-weight: 600;
                color: #1D1D1F;
            }
            QLabel#qrHolder {
                background-color: #F5F5F7;
                border-radius: 12px;
                border: 1px solid #E5E5E5;
            }
            QLabel#statusText {
                font-size: 14px;
                color: #86868B;
            }
            QPushButton {
                background-color: #E8E8ED;
                color: #1D1D1F;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #DCDCE0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("微信扫码登录")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 二维码图片容器
        self.qr_label = QLabel()
        self.qr_label.setObjectName("qrHolder")
        self.qr_label.setFixedSize(260, 260)
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setText("加载中...")
        layout.addWidget(self.qr_label, alignment=Qt.AlignCenter)
        
        # 状态文本
        self.status_label = QLabel("正在获取二维码...")
        self.status_label.setObjectName("statusText")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.refresh_btn = QPushButton("刷新二维码")
        self.refresh_btn.clicked.connect(self.on_refresh)
        btn_layout.addWidget(self.refresh_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.on_cancel)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def set_qr_image(self, image_bytes: bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        scaled = pixmap.scaled(240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.qr_label.setPixmap(scaled)
    
    def set_status(self, text: str):
        self.status_label.setText(text)
    
    def on_refresh(self):
        if self.cancel_event:
            self.cancel_event.set()
        self.status_label.setText("正在刷新...")
        self.qr_label.clear()
        self.qr_label.setText("加载中...")
        # 发信号让主窗口重新启动登录
        if self.parent():
            self.parent().start_qr_login()
    
    def on_cancel(self):
        if self.cancel_event:
            self.cancel_event.set()
        self.reject()


# ═══════════════════════════════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """91160 智慧分诊助手主窗口 - 企业级 Mac 风格"""
    
    def __init__(self):
        super().__init__()
        
        self.client = HealthClient()
        self.signals = WorkerSignals()
        self.cities: List[Dict] = []
        self.is_running = False
        self.is_logged_in = False
        self.login_checked = False
        self.pending_doctor_query = False
        self.pending_hospital_load = False
        self.pending_dep_load = False
        self.grab_stop_event = threading.Event()
        self.grab_thread: Optional[threading.Thread] = None
        self.qr_dialog: Optional[QRLoginDialog] = None
        self._combo_cache: Dict[QComboBox, List[tuple]] = {}
        self._combo_static: Dict[QComboBox, List[tuple]] = {}
        
        self._setup_window()
        self._build_ui()
        self._init_combo_filtering()
        self._connect_signals()
        self._init_data()
    
    def _setup_window(self):
        self.setWindowTitle("91160 智慧分诊助手")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        self.setStyleSheet(MAC_STYLE)
    
    def _add_shadow(self, widget, blur=30, y_offset=4, opacity=25):
        """为控件添加柔和阴影"""
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setXOffset(0)
        shadow.setYOffset(y_offset)
        shadow.setColor(QColor(0, 0, 0, opacity))
        widget.setGraphicsEffect(shadow)
    
    def _create_card(self) -> QFrame:
        """创建带阴影的卡片"""
        card = QFrame()
        card.setObjectName("card")
        self._add_shadow(card, blur=30, y_offset=4, opacity=20)
        return card
    
    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background-color: #F5F5F7;")
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(20)
        
        # ─────────────────────────────────────────────────────────────────
        # 顶部栏
        # ─────────────────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(16)
        
        # 标题
        title = QLabel("🏥 91160 智慧分诊助手")
        title.setObjectName("title")
        top_bar.addWidget(title)
        
        top_bar.addStretch()
        
        # 登录状态指示器
        status_container = QHBoxLayout()
        status_container.setSpacing(6)
        
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #FF3B30; font-size: 10px; background: transparent;")
        status_container.addWidget(self.status_dot)
        
        self.status_label = QLabel("未登录")
        self.status_label.setStyleSheet("color: #86868B; font-size: 14px; background: transparent;")
        status_container.addWidget(self.status_label)
        
        top_bar.addLayout(status_container)
        
        # 登录按钮
        self.login_btn = QPushButton("扫码登录")
        self.login_btn.setObjectName("secondary")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.on_login_click)
        top_bar.addWidget(self.login_btn)
        
        main_layout.addLayout(top_bar)
        
        # ─────────────────────────────────────────────────────────────────
        # 内容区域 (左右分栏)
        # ─────────────────────────────────────────────────────────────────
        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)
        
        # ═══════════════════════════════════════════════════════════════
        # 左侧：任务配置卡片
        # ═══════════════════════════════════════════════════════════════
        left_card = self._create_card()
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(28, 24, 28, 28)
        left_layout.setSpacing(20)
        
        # 卡片标题
        section_title = QLabel("📋 任务配置")
        section_title.setObjectName("sectionTitle")
        left_layout.addWidget(section_title)
        
        # 表单区域
        form_layout = QVBoxLayout()
        form_layout.setSpacing(16)
        
        # 城市
        form_layout.addWidget(self._create_field_label("所在城市"))
        self.city_combo = QComboBox()
        self.city_combo.setPlaceholderText("请选择城市")
        self.city_combo.setCursor(Qt.PointingHandCursor)
        self.city_combo.currentIndexChanged.connect(self.on_city_changed)
        form_layout.addWidget(self.city_combo)
        
        # 医院
        form_layout.addWidget(self._create_field_label("就诊医院"))
        self.hospital_combo = QComboBox()
        self.hospital_combo.setPlaceholderText("请先选择城市")
        self.hospital_combo.setCursor(Qt.PointingHandCursor)
        self.hospital_combo.currentIndexChanged.connect(self.on_hospital_changed)
        form_layout.addWidget(self.hospital_combo)
        
        # 科室
        form_layout.addWidget(self._create_field_label("目标科室"))
        self.dep_combo = QComboBox()
        self.dep_combo.setPlaceholderText("请先选择医院")
        self.dep_combo.setCursor(Qt.PointingHandCursor)
        self.dep_combo.currentIndexChanged.connect(self.on_dep_changed)
        form_layout.addWidget(self.dep_combo)
        
        # 就诊人
        form_layout.addWidget(self._create_field_label("就诊人"))
        self.member_combo = QComboBox()
        self.member_combo.setPlaceholderText("请先登录")
        self.member_combo.setCursor(Qt.PointingHandCursor)
        form_layout.addWidget(self.member_combo)
        
        # 日期
        form_layout.addWidget(self._create_field_label("就诊日期"))
        self.date_edit = QDateEdit()
        self.date_edit.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        self.date_edit.setCalendarPopup(True)
        today = QDate.currentDate()
        self.date_edit.setMinimumDate(today)
        self.date_edit.setMaximumDate(today.addDays(30))
        self.date_edit.setDate(today.addDays(7))
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCursor(Qt.PointingHandCursor)
        self.date_edit.dateChanged.connect(self.on_date_changed)
        form_layout.addWidget(self.date_edit)
        
        # 医生
        form_layout.addWidget(self._create_field_label("指定医生"))
        self.doctor_combo = QComboBox()
        self.doctor_combo.setPlaceholderText("全部医生 (默认)")
        self.doctor_combo.setCursor(Qt.PointingHandCursor)
        form_layout.addWidget(self.doctor_combo)
        
        left_layout.addLayout(form_layout)
        left_layout.addStretch()
        
        # 开始按钮
        self.start_btn = QPushButton("🚀 开始抢号")
        self.start_btn.setObjectName("primary")
        self.start_btn.setMinimumHeight(52)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle_grab)
        left_layout.addWidget(self.start_btn)
        
        left_card.setFixedWidth(400)
        content_layout.addWidget(left_card)
        
        # ═══════════════════════════════════════════════════════════════
        # 右侧：实时日志卡片
        # ═══════════════════════════════════════════════════════════════
        right_card = self._create_card()
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(28, 24, 28, 28)
        right_layout.setSpacing(16)
        
        # 标题行
        log_header = QHBoxLayout()
        log_title = QLabel("📜 实时日志")
        log_title.setObjectName("sectionTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("secondary")
        clear_btn.setFixedWidth(80)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_logs)
        log_header.addWidget(clear_btn)
        
        right_layout.addLayout(log_header)
        
        # 日志区域
        self.log_view = QTextEdit()
        self.log_view.setObjectName("logViewer")
        self.log_view.setReadOnly(True)
        right_layout.addWidget(self.log_view)
        
        content_layout.addWidget(right_card)
        
        main_layout.addLayout(content_layout)
    
    def _create_field_label(self, text: str) -> QLabel:
        """创建表单字段标签"""
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _init_combo_filtering(self):
        """让下拉框支持输入并动态筛选"""
        for combo in (
            self.city_combo,
            self.hospital_combo,
            self.dep_combo,
            self.member_combo,
            self.doctor_combo,
        ):
            self._make_combo_filterable(combo)

    def _make_combo_filterable(self, combo: QComboBox):
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        line_edit = combo.lineEdit()
        if line_edit:
            line_edit.setClearButtonEnabled(True)
            line_edit.textEdited.connect(
                lambda text, c=combo: self._filter_combo_items(c, text)
            )

    def _set_combo_items(
        self,
        combo: QComboBox,
        items: List[tuple],
        static_items: Optional[List[tuple]] = None,
        select_first: bool = True,
    ):
        self._combo_cache[combo] = items
        static_items = static_items or []
        self._combo_static[combo] = static_items
        text = combo.lineEdit().text() if combo.isEditable() else ""
        self._refresh_combo_items(combo, text, select_first=select_first, show_popup=False)

    def _refresh_combo_items(
        self,
        combo: QComboBox,
        text: str,
        select_first: bool,
        show_popup: bool,
    ):
        items = self._combo_cache.get(combo, [])
        static_items = self._combo_static.get(combo, [])
        keyword = (text or "").strip().lower()
        if keyword:
            filtered = [i for i in items if keyword in str(i[0]).lower()]
        else:
            filtered = items

        line_edit = combo.lineEdit()
        cursor_pos = line_edit.cursorPosition() if line_edit else 0
        with QSignalBlocker(combo):
            combo.clear()
            for t, d in static_items:
                combo.addItem(t, d)
            for t, d in filtered:
                combo.addItem(t, d)
            if select_first and (static_items or filtered):
                combo.setCurrentIndex(0)
            else:
                combo.setCurrentIndex(-1)

        if line_edit:
            line_edit.setText(text)
            line_edit.setCursorPosition(min(cursor_pos, len(text)))
        if show_popup and combo.hasFocus() and combo.count() > 0:
            combo.showPopup()

    def _filter_combo_items(self, combo: QComboBox, text: str):
        self._refresh_combo_items(combo, text, select_first=False, show_popup=True)
    
    def _connect_signals(self):
        """连接后台信号"""
        self.signals.log.connect(self._append_log)
        self.signals.hospitals_loaded.connect(self._update_hospitals)
        self.signals.deps_loaded.connect(self._update_deps)
        self.signals.doctors_loaded.connect(self._update_doctors)
        self.signals.members_loaded.connect(self._update_members)
        self.signals.login_status.connect(self._update_login_status)
        self.signals.qr_image.connect(self._show_qr_image)
        self.signals.qr_status.connect(self._update_qr_status)
        self.signals.qr_close.connect(self._close_qr_dialog)
        self.signals.update_button.connect(self._update_start_button)
    
    def _init_data(self):
        """初始化数据"""
        self.log("正在初始化...")
        
        # 加载城市列表
        cities_file = os.path.join(os.path.dirname(__file__), 'cities.json')
        if os.path.exists(cities_file):
            with open(cities_file, 'r', encoding='utf-8') as f:
                self.cities = json.load(f)
                items = [(city['name'], city['cityId']) for city in self.cities]
                self._set_combo_items(self.city_combo, items, select_first=True)
            self.log(f"已加载 {len(self.cities)} 个城市")
            if self.cities:
                self.on_city_changed(0)
        
        # 检查登录状态
        def check_login():
            try:
                if self.client.load_cookies():
                    members = self.client.get_members()
                    if members:
                        self.signals.login_status.emit(True)
                        self.signals.members_loaded.emit(members)
                        self.signals.log.emit("登录状态验证成功", "#00D26A")
                    else:
                        self.signals.login_status.emit(False)
                        self.signals.log.emit("Cookie 已过期，请重新登录", "#FF9500")
                else:
                    self.signals.login_status.emit(False)
                    self.signals.log.emit("需要登录", "#FF9500")
            except Exception as e:
                self.signals.log.emit(f"初始化失败: {e}", "#FF3B30")
        
        threading.Thread(target=check_login, daemon=True).start()
    
    # ─────────────────────────────────────────────────────────────────
    # 日志相关
    # ─────────────────────────────────────────────────────────────────
    
    def log(self, message: str, color: str = "#AAAAAA"):
        self.signals.log.emit(message, color)
    
    def _append_log(self, message: str, color: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_message = html.escape(message)
        safe_message = safe_message.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
        html_line = (
            f'<span style="color: #666666;">[{timestamp}]</span> '
            f'<span style="color: {color};">{safe_message}</span><br>'
        )
        self.log_view.insertHtml(html_line)
        self.log_view.ensureCursorVisible()

    def _emit_grab_log(self, message: str, level: str = "info"):
        color_map = {
            "info": "#AAAAAA",
            "success": "#00D26A",
            "warn": "#FF9500",
            "error": "#FF3B30",
        }
        self.signals.log.emit(message, color_map.get(level, "#AAAAAA"))

    def _build_grab_config(self) -> Dict:
        unit_id = self.hospital_combo.currentData()
        dep_id = self.dep_combo.currentData()
        doctor_id = self.doctor_combo.currentData()
        member_id = self.member_combo.currentData()
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        return {
            "unit_id": str(unit_id),
            "unit_name": self.hospital_combo.currentText(),
            "dep_id": str(dep_id),
            "dep_name": self.dep_combo.currentText(),
            "doctor_ids": [str(doctor_id)] if doctor_id not in (None, "") else [],
            "member_id": str(member_id),
            "member_name": self.member_combo.currentText(),
            "target_dates": [date_str],
            "time_types": ["am", "pm"],
            "preferred_hours": [],
        }
    
    def clear_logs(self):
        self.log_view.clear()
    
    # ─────────────────────────────────────────────────────────────────
    # 下拉框联动
    # ─────────────────────────────────────────────────────────────────
    
    def on_city_changed(self, index: int):
        if index < 0:
            return
        city_id = self.city_combo.currentData()
        if not city_id:
            return
        if not self.login_checked:
            if not self.pending_hospital_load:
                self.log("登录状态验证中，稍后自动加载医院", "#FF9500")
            self.pending_hospital_load = True
            return
        if not self.is_logged_in:
            self.log("未登录，无法加载医院", "#FF3B30")
            self.pending_hospital_load = True
            return
        self.log(f"正在加载城市 {self.city_combo.currentText()} 的医院...")
        self.hospital_combo.clear()
        self.hospital_combo.addItem("加载中...", "")
        
        def load():
            try:
                units = self.client.get_hospitals_by_city(city_id)
                self.signals.hospitals_loaded.emit(units)
            except Exception as e:
                self.signals.log.emit(f"加载医院失败: {e}", "#FF3B30")
        
        threading.Thread(target=load, daemon=True).start()
    
    def _update_hospitals(self, units: list):
        items = [(u.get('unit_name', ''), u.get('unit_id', '')) for u in units or []]
        self._set_combo_items(self.hospital_combo, items, select_first=True)
        self.log(f"已加载 {len(items)} 家医院", "#00D26A")
        if items:
            self.on_hospital_changed(0)
    
    def on_hospital_changed(self, index: int):
        if index < 0:
            return
        unit_id = self.hospital_combo.currentData()
        if not unit_id:
            return
        if not self.login_checked:
            if not self.pending_dep_load:
                self.log("登录状态验证中，稍后自动加载科室", "#FF9500")
            self.pending_dep_load = True
            return
        if not self.is_logged_in:
            self.log("未登录，无法加载科室", "#FF3B30")
            self.pending_dep_load = True
            return
        
        self.log(f"正在加载科室...")
        self.dep_combo.clear()
        self.dep_combo.addItem("加载中...", "")
        
        def load():
            try:
                deps = self.client.get_deps_by_unit(unit_id)
                self.signals.deps_loaded.emit(deps)
            except Exception as e:
                self.signals.log.emit(f"加载科室失败: {e}", "#FF3B30")
        
        threading.Thread(target=load, daemon=True).start()
    

    def _update_deps(self, deps: list):
        items: List[tuple] = []
        for item in deps or []:
            if isinstance(item, dict) and isinstance(item.get("childs"), list):
                for child in item.get("childs", []):
                    name = child.get("dep_name") or child.get("name", "")
                    dep_id = child.get("dep_id") or child.get("id", "")
                    if name and dep_id not in (None, ""):
                        items.append((name, dep_id))
            elif isinstance(item, dict):
                name = item.get("dep_name") or item.get("name", "")
                dep_id = item.get("dep_id") or item.get("id", "")
                if name and dep_id not in (None, ""):
                    items.append((name, dep_id))
        if not items:
            self._set_combo_items(
                self.dep_combo,
                [],
                static_items=[("暂无科室", "")],
                select_first=True,
            )
        else:
            self._set_combo_items(self.dep_combo, items, select_first=True)
        self.log(f"已加载 {len(items)} 个科室", "#00D26A")
        if items:
            self.on_dep_changed(0)

    def on_dep_changed(self, index: int):
        if index < 0:
            return
        self._load_doctors()
    
    def on_date_changed(self, date: QDate):
        self._load_doctors()
    
    def _load_doctors(self):
        unit_id = self.hospital_combo.currentData()
        dep_id = self.dep_combo.currentData()
        if unit_id in (None, "") or dep_id in (None, ""):
            return
        if not self.login_checked:
            if not self.pending_doctor_query:
                self.log("登录状态验证中，稍后自动查询排班", "#FF9500")
            self.pending_doctor_query = True
            return
        if not self.is_logged_in:
            self.log("未登录，无法查询排班", "#FF3B30")
            return

        date_value = self.date_edit.date()
        min_date = self.date_edit.minimumDate()
        max_date = self.date_edit.maximumDate()
        if date_value < min_date:
            date_value = min_date
            self.date_edit.setDate(date_value)
            self.log("就诊日期超出范围，已自动调整到最早可选日期", "#FF9500")
        elif date_value > max_date:
            date_value = max_date
            self.date_edit.setDate(date_value)
            self.log("就诊日期超出范围，已自动调整到最晚可选日期", "#FF9500")
        date_str = date_value.toString("yyyy-MM-dd")

        self.log(f"正在查询 {date_str} 的排班...")
        self.doctor_combo.clear()
        self.doctor_combo.addItem("查询中...", "")
        
        def load():
            try:
                docs = self.client.get_schedule(unit_id, dep_id, date_str)
                self.signals.doctors_loaded.emit(docs)
                if docs:
                    self.signals.log.emit(f"发现 {len(docs)} 位医生有排班", "#00D26A")
                else:
                    err = getattr(self.client, "last_error", None)
                    if err:
                        self.signals.log.emit(err, "#FF3B30")
                        if "登录" in err or "access_hash" in err:
                            self.signals.login_status.emit(False)
                    else:
                        self.signals.log.emit("该日期无号源", "#FF9500")
            except Exception as e:
                self.signals.log.emit(f"查询排班失败: {e}", "#FF3B30")
        
        threading.Thread(target=load, daemon=True).start()
    

    def _update_doctors(self, docs: list):
        items: List[tuple] = []
        for d in docs or []:
            left = d.get('total_left_num', '?')
            fee = d.get('reg_fee', '?')
            name = d.get('doctor_name', '')
            text = f"{name} (余{left}/￥{fee})"
            items.append((text, d.get('doctor_id')))
        self._set_combo_items(
            self.doctor_combo,
            items,
            static_items=[("全部医生 (默认)", "")],
            select_first=True,
        )

    def _update_members(self, members: list):
        items = [(m.get('name', ''), m.get('id', '')) for m in members or []]
        self._set_combo_items(self.member_combo, items, select_first=True)
    
    def _update_login_status(self, logged_in: bool):
        self.is_logged_in = logged_in
        self.login_checked = True
        if logged_in:
            self.status_dot.setStyleSheet("color: #34C759; font-size: 10px; background: transparent;")
            self.status_label.setText("已登录")
        else:
            self.status_dot.setStyleSheet("color: #FF3B30; font-size: 10px; background: transparent;")
            self.status_label.setText("未登录")
        if logged_in and self.pending_hospital_load:
            self.pending_hospital_load = False
            self.pending_dep_load = False
            self.on_city_changed(self.city_combo.currentIndex())
        elif logged_in and self.pending_dep_load:
            self.pending_dep_load = False
            self.on_hospital_changed(self.hospital_combo.currentIndex())
        if logged_in and self.pending_doctor_query:
            self.pending_doctor_query = False
            self._load_doctors()
    
    # ─────────────────────────────────────────────────────────────────
    # 登录相关
    # ─────────────────────────────────────────────────────────────────
    
    def on_login_click(self):
        self.qr_dialog = QRLoginDialog(self)
        self.qr_dialog.show()
        self.start_qr_login()
    
    def start_qr_login(self):
        """启动二维码登录流程"""
        self.log("正在启动浏览器，请稍候...")
        
        def run_login():
            # 使用同步的 FastQRLogin，避免 asyncio 环境问题
            from core.qr_login import FastQRLogin, QRLoginResult
            
            # 使用列表作为可变引用传递停止标志
            stop_flag = [False]
            
            # 保存到 dialog 以便取消
            if self.qr_dialog:
                self.qr_dialog.stop_flag = stop_flag
            
            def on_qr(qr_bytes: bytes):
                self.signals.log.emit(f"收到二维码 ({len(qr_bytes)} bytes)", "#00D26A")
                self.signals.qr_image.emit(qr_bytes)
            
            def on_status(msg: str):
                self.signals.log.emit(f"登录状态: {msg}", "#AAAAAA")
                self.signals.qr_status.emit(msg)
            
            try:
                # 显式导入避免命名空间问题
                login = FastQRLogin()
                
                # 1. 获取二维码
                try:
                    on_status("正在获取二维码...")
                    qr_bytes, uuid = login.get_qr_image()
                    on_qr(qr_bytes)
                    on_status("请使用微信扫码")
                except Exception as e:
                    self.signals.qr_status.emit(f"获取二维码失败: {e}")
                    self.signals.log.emit(f"获取二维码失败: {e}", "#FF3B30")
                    self.signals.grab_finished.emit(False, str(e))
                    return

                # 2. 轮询状态
                try:
                    result = login.poll_status(
                        timeout_sec=300, 
                        on_status=on_status, 
                        stop_flag=stop_flag
                    )
                except Exception as e:
                    result = QRLoginResult(False, f"轮询异常: {e}")

                if result.success:
                    self.signals.log.emit(f"登录成功! Cookie已保存: {result.cookie_path}", "#00D26A")
                    self.signals.login_status.emit(True)
                    
                    # 重新加载就诊人
                    try:
                        self.client.load_cookies()
                        members = self.client.get_members()
                        self.signals.members_loaded.emit(members)
                    except Exception as e:
                        self.signals.log.emit(f"加载就诊人失败: {e}", "#FF9500")

                    # 关闭对话框
                    self.signals.qr_close.emit()
                    
                    self.signals.grab_finished.emit(True, "登录成功")
                else:
                    msg = result.message or "未知错误"
                    if msg != "已取消":
                        self.signals.log.emit(f"登录失败: {msg}", "#FF3B30")
                    self.signals.grab_finished.emit(False, msg)
                    
            except Exception as e:
                self.signals.log.emit(f"登录过程发生错误: {e}", "#FF3B30")
                import traceback
                traceback.print_exc()
                self.signals.grab_finished.emit(False, str(e))
        
        # 在新线程中运行同步登录逻辑
        threading.Thread(target=run_login, daemon=True).start()
    
    async def _create_cancel_event(self):
        """在当前事件循环中创建 cancel_event"""
        return asyncio.Event()
    
    def _show_qr_image(self, image_bytes: bytes):
        if self.qr_dialog:
            self.qr_dialog.set_qr_image(image_bytes)
    
    def _update_qr_status(self, text: str):
        if self.qr_dialog:
            self.qr_dialog.set_status(text)

    def _close_qr_dialog(self):
        if self.qr_dialog:
            self.qr_dialog.accept()
    
    # ─────────────────────────────────────────────────────────────────
    # 抢号逻辑
    # ─────────────────────────────────────────────────────────────────
    
    def _update_start_button(self, text: str, object_name: str):
        self.start_btn.setText(text)
        self.start_btn.setObjectName(object_name)
        # 强制刷新样式
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
    
    def toggle_grab(self):
        if self.is_running:
            self.is_running = False
            self.grab_stop_event.set()
            self.signals.update_button.emit("🚀 开始抢号", "primary")
            self.log("任务已手动停止", "#FF9500")
        else:
            # 校验
            if not self.hospital_combo.currentData():
                self.log("⚠️ 请先选择医院！", "#FF3B30")
                return
            if not self.dep_combo.currentData():
                self.log("⚠️ 请先选择科室！", "#FF3B30")
                return
            if not self.member_combo.currentData():
                self.log("⚠️ 请先选择就诊人！", "#FF3B30")
                return
            
            self.is_running = True
            self.grab_stop_event.clear()
            self.signals.update_button.emit("⏹️ 停止抢号", "danger")
            
            self.log(">>> 启动高频抢号引擎 <<<", "#00D26A")
            self.log(f"目标日期: {self.date_edit.date().toString('yyyy-MM-dd')}")
            
            # 启动抢号线程
            self.grab_thread = threading.Thread(target=self._grab_loop, daemon=True)
            self.grab_thread.start()
    
    def _grab_loop(self):
        """抢号主循环（真实抢号）"""
        from core.grab import grab
        import time

        grab_client = HealthClient()
        grab_client.load_cookies()
        has_access_hash = any(
            c.name == "access_hash" and c.value
            for c in grab_client.session.cookies
        )
        if not has_access_hash:
            self.signals.log.emit("缺少 access_hash，请重新扫码登录", "#FF3B30")
            self.signals.login_status.emit(False)
            self.is_running = False
            self.signals.update_button.emit("🚀 开始抢号", "primary")
            return

        config = self._build_grab_config()
        retry_interval = 0.5
        attempt = 0

        while self.is_running and not self.grab_stop_event.is_set():
            attempt += 1
            self.signals.log.emit(f"第 {attempt} 次尝试...", "#FFFFFF")

            success = grab(
                config,
                grab_client,
                on_log=self._emit_grab_log,
                stop_event=self.grab_stop_event,
            )

            if success:
                self.signals.log.emit("抢号成功，任务结束", "#00D26A")
                break

            last_error = getattr(grab_client, "last_error", "") or ""
            if "登录" in last_error or "access_hash" in last_error:
                self.signals.log.emit(last_error, "#FF3B30")
                self.signals.login_status.emit(False)
                break

            if not self.is_running or self.grab_stop_event.is_set():
                break

            time.sleep(retry_interval)

        self.is_running = False
        self.signals.update_button.emit("🚀 开始抢号", "primary")
        if self.grab_stop_event.is_set():
            self.signals.log.emit("抢号任务已停止", "#FF9500")
        else:
            self.signals.log.emit("抢号任务已结束", "#FF9500")


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 跨平台一致性
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
