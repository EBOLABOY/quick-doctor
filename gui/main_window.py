from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit, 
                             QGroupBox, QFormLayout, QMessageBox, QDateEdit, QCompleter,
                             QDialog, QCheckBox, QScrollArea, QDialogButtonBox)
from PyQt6.QtCore import Qt, QDate, QSortFilterProxyModel
from PyQt6.QtGui import QFont
from core.client import HealthClient
from .workers import GrabWorker, ResourceLoader
import json
import os

def setup_searchable_combo(combo: QComboBox):
    """为可编辑的ComboBox设置支持包含匹配的Completer，并增强交互体验"""
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # 禁止插入用户输入
    
    completer = QCompleter(combo.model(), combo)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    combo.setCompleter(completer)
    
    # 输入时触发下拉显示
    combo.lineEdit().textEdited.connect(lambda text: combo.showPopup() if text else None)

class DoctorSelectDialog(QDialog):
    def __init__(self, doctors, parent=None):
        super().__init__(parent)
        self.setWindowTitle("多选/预测医生")
        self.resize(500, 400)
        self.selected_ids = []
        
        layout = QVBoxLayout(self)

        # 提示
        tips = QLabel("以下是未来7天内有排班的医生，勾选后将加入抢号目标：")
        tips.setWordWrap(True)
        layout.addWidget(tips)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.check_layout = QVBoxLayout(content)
        
        self.checkboxes = []
        
        for doc in doctors:
            name = doc.get('doctor_name')
            did = str(doc.get('doctor_id'))
            skill = doc.get('skill', '')[:20] + '...' if doc.get('skill') else ''
            
            # Label text
            txt = f"{name}"
            if 'source_date' in doc:
                txt += f" (最近出诊: {doc['source_date']})"
            
            chk = QCheckBox(txt)
            chk.setProperty('doc_id', did)
            self.check_layout.addWidget(chk)
            self.checkboxes.append(chk)
            
        self.check_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet("""
            QDialog { background-color: #F5F5F7; }
            QScrollArea { border: none; background-color: white; border-radius: 6px; }
            QWidget { background-color: white; }
            QCheckBox { padding: 5px; font-size: 13px; }
            QLabel { background-color: transparent; }
        """)

    def get_selected(self):
        res = []
        names = []
        for chk in self.checkboxes:
            if chk.isChecked():
                res.append(chk.property('doc_id'))
                names.append(chk.text().split(' ')[0])
        return res, names

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("医院自动挂号助手")
        self.resize(1100, 750)
        
        self.client = HealthClient()
        self.worker = None
        self.loader = ResourceLoader(self.client)
        self.loader.data_loaded.connect(self.on_data_loaded)
        
        self.config = self.load_config()
        
        # 缓存数据
        self.hospitals = [] # [{'unit_id':..., 'unit_name':...}]
        self.deps = []      # [{'dep_id':..., 'dep_name':...}]
        self.doctors = []   # [{'doctor_id':..., 'doctor_name':...}]

        self.apply_mac_theme()
        self.setup_ui()
        self.init_data()

    def apply_mac_theme(self):
        style = """
        QMainWindow, QWidget { 
            background-color: #F5F5F7; 
            color: #1D1D1F; 
            font-family: "Segoe UI", "Microsoft YaHei"; 
        }
        
        QGroupBox { 
            background-color: #FFFFFF; 
            border: 1px solid #D1D1D6; 
            border-radius: 8px; 
            margin-top: 10px; 
            font-weight: bold; 
            padding-top: 15px;
        }
        QGroupBox::title { 
            subcontrol-origin: margin; 
            subcontrol-position: top left; 
            padding: 0 5px; 
            left: 10px;
            color: #333;
        }
        
        QLineEdit, QComboBox, QDateEdit, QTextEdit { 
            background-color: #FFFFFF; 
            border: 1px solid #D1D1D6; 
            padding: 6px; 
            border-radius: 6px; 
            color: #1D1D1F; 
            selection-background-color: #007AFF;
            font-family: "Arial", "Segoe UI", sans-serif;
        }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
            border: 1px solid #007AFF;
        }
        
        QComboBox::drop-down { border: 0px; }
        
        QPushButton { 
            background-color: #007AFF; 
            color: white; 
            border: none; 
            padding: 8px 16px; 
            border-radius: 6px; 
            font-weight: bold; 
            font-size: 13px;
        }
        QPushButton:hover { background-color: #0069D9; }
        QPushButton:pressed { background-color: #0056B3; }
        QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        
        QLabel { color: #1D1D1F; }
        """
        self.setStyleSheet(style)

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # == 左侧控制区 ==
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addLayout(left_layout, stretch=1)

        # 1. 账号模块
        acct_box = QGroupBox("账号信息")
        acct_frm = QFormLayout()
        self.lbl_status = QLabel("Checking...")
        self.btn_login = QPushButton("刷新Cookie/登录")
        self.btn_login.clicked.connect(self.do_login)
        self.btn_login.setStyleSheet("background-color: #2196F3;")
        acct_frm.addRow("状态:", self.lbl_status)
        acct_frm.addRow(self.btn_login)
        acct_box.setLayout(acct_frm)
        left_layout.addWidget(acct_box)

        # 2. 挂号设置模块
        conf_box = QGroupBox("挂号筛选")
        conf_frm = QFormLayout()

        # 城市选择 (可输入搜索)
        self.cb_city = QComboBox()
        self.cb_city.setEditable(True)
        self.cb_city.setPlaceholderText("输入城市名或拼音搜索...")
        # 加载城市列表
        self.cities = []
        cities_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cities.json')
        try:
            with open(cities_file, 'r', encoding='utf-8') as f:
                self.cities = json.load(f)
        except Exception as e:
            print(f"城市列表加载失败: {e}")
        
        for c in self.cities:
            # 显示名称，存储ID，match字段用于搜索
            self.cb_city.addItem(c.get('name', ''), c.get('cityId', ''))
        self.cb_city.setCurrentIndex(0)  # 默认深圳
        setup_searchable_combo(self.cb_city)  # 启用包含搜索
        self.cb_city.currentIndexChanged.connect(self.on_city_changed)

        # 医院 (Cascading 1)
        self.cb_hospital = QComboBox()
        self.cb_hospital.setEditable(True)
        self.cb_hospital.setPlaceholderText("选择或搜索医院...")
        self.cb_hospital.currentIndexChanged.connect(self.on_hospital_changed)
        
        # 科室 (Cascading 2)
        self.cb_dep = QComboBox()
        self.cb_dep.setEditable(True)
        self.cb_dep.setPlaceholderText("先选医院...")
        self.cb_dep.currentIndexChanged.connect(self.on_dep_changed)

        # 日期 (使用 QLineEdit 避免 QDateEdit 字体渲染问题)
        from datetime import datetime, timedelta
        default_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        self.input_date = QLineEdit(default_date)
        self.input_date.setPlaceholderText("格式: YYYY-MM-DD (如 2026-01-29)")
        self.input_date.editingFinished.connect(self.trigger_load_doctors)

        # 医生 (Cascading 3)
        self.cb_doctor = QComboBox()
        self.cb_doctor.setEditable(True)
        self.cb_doctor.setPlaceholderText("可选择特定医生 (默认全选)")
        setup_searchable_combo(self.cb_doctor)
        
        # 多选/预测按钮
        self.btn_multi = QPushButton("✚ 多选/预测")
        self.btn_multi.setFixedWidth(100)
        self.btn_multi.clicked.connect(self.trigger_predict_doctors)
        
        # 刷新按钮
        btn_refresh_doc = QPushButton("↻")
        btn_refresh_doc.setFixedWidth(30)
        btn_refresh_doc.clicked.connect(self.trigger_load_doctors)
        
        doc_layout = QHBoxLayout()
        doc_layout.addWidget(self.cb_doctor)
        doc_layout.addWidget(self.btn_multi)
        doc_layout.addWidget(btn_refresh_doc)

        conf_frm.addRow("所在城市:", self.cb_city)
        conf_frm.addRow("就诊医院:", self.cb_hospital)
        conf_frm.addRow("目标科室:", self.cb_dep)
        conf_frm.addRow("就诊日期:", self.input_date)
        conf_frm.addRow("指定医生:", doc_layout)
        
        # 就诊人
        self.cb_member = QComboBox()
        conf_frm.addRow("就诊人:", self.cb_member)

        conf_box.setLayout(conf_frm)
        left_layout.addWidget(conf_box)

        # 3. 执行控制
        act_box = QGroupBox("执行任务")
        act_layout = QVBoxLayout()
        
        # 时间
        self.input_time = QLineEdit(self.config.get('start_time', ''))
        self.input_time.setPlaceholderText("定时启动 (HH:MM:SS) 留空立即")
        act_layout.addWidget(QLabel("定时开始:"))
        act_layout.addWidget(self.input_time)
        
        self.btn_start = QPushButton("开始抢号")
        self.btn_start.setFixedHeight(50)
        self.btn_start.clicked.connect(self.toggle_task)
        act_layout.addWidget(self.btn_start)
        
        act_box.setLayout(act_layout)
        left_layout.addWidget(act_box)

        # == 右侧日志区 ==
        right_layout = QVBoxLayout()
        layout.addLayout(right_layout, stretch=2)
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("font-family: Consolas; font-size: 12px;")
        right_layout.addWidget(QLabel("实时日志:"))
        right_layout.addWidget(self.log_area)

    def init_data(self):
        self.log("初始化数据...")
        if self.client.login():
            self.lbl_status.setText(f"已登录")
            self.lbl_status.setStyleSheet("color: #4CAF50;")
            self.load_members()
        else:
            self.lbl_status.setText("未登录")
            self.lbl_status.setStyleSheet("color: #f44336;")
            self.do_login()

        # 启动时加载医院列表 (耗时操作放在后台)
        self.log("正在加载医院列表...")
        self.cb_hospital.addItem("Loading...", None)
        city_id = self.cb_city.currentData() or "5"
        self.loader.fetch('hospitals', city_id)

    def do_login(self):
        self.log("启动浏览器登录...")
        if self.client.login():
            self.lbl_status.setText("已登录")
            self.lbl_status.setStyleSheet("color: #4CAF50;")
            self.log("登录成功")
            self.load_members()
        else:
            self.log("登录失败")
    
    def load_members(self):
        mems = self.client.get_members()
        self.cb_member.clear()
        if mems:
            for m in mems:
                self.cb_member.addItem(m['name'], m['id'])
            # Restore
            curr = str(self.config.get('member_id', ''))
            idx = self.cb_member.findData(curr)
            if idx >= 0: self.cb_member.setCurrentIndex(idx)

    # == Cascading Logic ==

    def on_data_loaded(self, key, data):
        if key == 'hospitals':
            self.hospitals = data if isinstance(data, list) else []
            self.cb_hospital.blockSignals(True)
            self.cb_hospital.clear()
            self.cb_hospital.addItem("--- 请选择医院 ---", None)
            
            target_id = str(self.config.get('unit_id', ''))
            target_idx = 0
            
            for h in self.hospitals:
                uid = str(h.get('unit_id', h.get('id')))
                name = h.get('unit_name', h.get('name'))
                self.cb_hospital.addItem(name, uid)
                if uid == target_id: target_idx = self.cb_hospital.count() - 1
            
            self.cb_hospital.blockSignals(False)
            self.log(f"加载了 {len(self.hospitals)} 家医院")
            
            # 启用搜索
            setup_searchable_combo(self.cb_hospital)  # 启用包含搜索
            
            # 恢复选中
            if target_idx > 0:
                self.cb_hospital.setCurrentIndex(target_idx) # 会触发 on_hospital_changed
                
        elif key == 'deps':
            # Flatten deps
            self.deps = []
            if isinstance(data, list):
                for cat in data:
                    if 'childs' in cat:
                        for child in cat['childs']:
                            self.deps.append(child)
                    elif 'dep_id' in cat:
                        self.deps.append(cat)
            
            self.cb_dep.blockSignals(True)
            self.cb_dep.clear()
            self.cb_dep.addItem("--- 请选择科室 ---", None)
            
            target_id = str(self.config.get('dep_id', ''))
            target_idx = 0
            
            for d in self.deps:
                did = str(d.get('dep_id', d.get('id')))
                name = d.get('dep_name', d.get('name'))
                self.cb_dep.addItem(name, did)
                if did == target_id: target_idx = self.cb_dep.count() - 1
            
            self.cb_dep.blockSignals(False)
            # 启用搜索
            setup_searchable_combo(self.cb_dep)  # 启用包含搜索
            self.log(f"加载了 {len(self.deps)} 个科室")
            
            if target_idx > 0:
                self.cb_dep.setCurrentIndex(target_idx)
                # Next: Doctors? only if date matches
                
        elif key == 'doctors':
            self.doctors = data if isinstance(data, list) else []
            self.cb_doctor.blockSignals(True)
            self.cb_doctor.clear()
            self.cb_doctor.addItem("所有医生 (默认)", [])
            
            count = 0
            if not self.doctors:
                self.cb_doctor.addItem("未查询到排班 (可直接抢号)", [])
            else:
                for doc in self.doctors:
                    schedules = doc.get('schedules', [])
                    # 统计号源
                    left = sum([int(str(s.get('left_num',0)).strip() or 0) for s in schedules])
                    state = "有号" if left > 0 else "无号"
                    
                    name = f"{doc.get('doctor_name')} ({state} {left})"
                    did = str(doc.get('doctor_id'))
                    self.cb_doctor.addItem(name, did)
                    if left > 0: count += 1
                
            self.cb_doctor.blockSignals(False)
            
            if not self.doctors:
                self.log("⚠️ 该日期未查询到排班，系统将尝试【盲抢模式】(监控所有医生)")
            else:
                self.log(f"加载了 {len(self.doctors)} 位医生 ({count} 有号)")

        elif key == 'doctors_forecast':
            self.btn_multi.setEnabled(True)
            self.btn_multi.setText("✚ 多选/预测")
            
            if not data:
                QMessageBox.information(self, "预测结果", "未来7天暂无医生排班信息")
                return
                
            dlg = DoctorSelectDialog(data, self)
            if dlg.exec():
                ids, names = dlg.get_selected()
                if ids:
                    self.log(f"已锁定预测目标: {','.join(names)}")
                    # 将选择结果回填到 cb_doctor 并锁定
                    self.cb_doctor.blockSignals(True)
                    self.cb_doctor.clear()
                    self.cb_doctor.addItem(f"已锁定 {len(ids)} 位预测医生", ids)
                    self.cb_doctor.setCurrentIndex(0)
                    self.cb_doctor.blockSignals(False)
                else:
                    self.log("未选择任何预测医生")

    def on_city_changed(self, idx):
        city_id = self.cb_city.currentData()
        if city_id:
            self.log(f"切换城市: {self.cb_city.currentText()}, 加载医院...")
            self.cb_hospital.clear()
            self.cb_hospital.addItem("Loading...", None)
            self.cb_dep.clear()
            self.cb_doctor.clear()
            self.loader.fetch('hospitals', city_id)

    def on_hospital_changed(self, idx):
        uid = self.cb_hospital.currentData()
        if uid:
            self.log(f"选中医院ID: {uid}, 加载科室...")
            self.cb_dep.clear()
            self.cb_dep.addItem("Loading...", None)
            self.loader.fetch('deps', uid)
        else:
            self.cb_dep.clear()

    def on_dep_changed(self, idx):
        did = self.cb_dep.currentData()
        if did:
            # self.trigger_load_doctors() # 可选是否自动加载
            pass

    def trigger_load_doctors(self):
        uid = self.cb_hospital.currentData()
        did = self.cb_dep.currentData()
        date = self.input_date.text().strip()
        
        if uid and did and date:
            self.log(f"查询医生排班: {date}...")
            self.cb_doctor.clear()
            self.cb_doctor.addItem("Loading...", None)
            self.loader.fetch('doctors', uid, did, date)

    def toggle_task(self):
        if self.worker and self.worker.is_running:
            self.worker.stop()
            self.worker.wait()
            self.worker = None
            self.btn_start.setText("开始抢号")
            self.btn_start.setStyleSheet("background-color: #4CAF50;") 
            self.log("任务停止")
        else:
            # Collect Config
            uid = self.cb_hospital.currentData()
            did = self.cb_dep.currentData()
            mid = self.cb_member.currentData()
            if not (uid and did and mid):
                QMessageBox.warning(self, "参数不全", "请确保已选择医院、科室和就诊人")
                return

            config = {
                'unit_id': uid,
                'unit_name': self.cb_hospital.currentText(),
                'dep_id': did,
                'dep_name': self.cb_dep.currentText(),
                'member_id': mid,
                'member_name': self.cb_member.currentText(),
                'target_dates': [self.input_date.text().strip()],
                'start_time': self.input_time.text().strip(),
                'doctor_ids': []
            }
            
            # Doctor filter
            sel_doc_id = self.cb_doctor.currentData()
            if sel_doc_id:
                if isinstance(sel_doc_id, list):
                    config['doctor_ids'] = [str(x) for x in sel_doc_id]
                    if config['doctor_ids']:
                        self.log(f"锁定医生ID: {config['doctor_ids']}")
                    else:
                        self.log("模式: 抢该日期下有号的所有医生")
                elif isinstance(sel_doc_id, str) or isinstance(sel_doc_id, int):
                    config['doctor_ids'] = [str(sel_doc_id)]
                    self.log(f"锁定医生ID: {sel_doc_id}")
            else:
                self.log("模式: 抢该日期下有号的所有医生")

            # Save Config Back
            try:
                with open("config.json", "w", encoding="utf-8") as f:
                    # Update internal config object too (merge)
                    self.config.update(config)
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            except: pass

            self.worker = GrabWorker(config)
            self.worker.log_signal.connect(self.log)
            self.worker.finished_signal.connect(self.on_worker_finished)
            self.worker.start()
            
            self.btn_start.setText("停止抢号")
            self.btn_start.setStyleSheet("background-color: #f44336;")

    def on_worker_finished(self, success, msg):
        self.btn_start.setText("开始抢号")
        self.btn_start.setStyleSheet("background-color: #4CAF50;")
        if success:
             QMessageBox.information(self, "成功", msg)
        else:
             QMessageBox.warning(self, "结束", msg)

    def trigger_predict_doctors(self):
        uid = self.cb_hospital.currentData()
        did = self.cb_dep.currentData()
        date = self.input_date.text().strip()
        
        if not (uid and did and date):
            QMessageBox.warning(self, "提示", "请先选择医院、科室和起始日期")
            return
            
        self.log(f"正在扫描未来7天排班以预测医生名单 (基准日期: {date})...")
        self.btn_multi.setEnabled(False)
        self.loader.fetch('doctors_forecast', uid, did, date)

    def log(self, msg):
        self.log_area.append(msg)
