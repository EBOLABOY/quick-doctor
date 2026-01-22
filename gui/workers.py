from PyQt6.QtCore import QThread, pyqtSignal
from core.client import HealthClient
import datetime
import time

class GrabWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)  # success, message

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.is_running = True
        self.client = HealthClient()

    def log(self, msg):
        self.log_signal.emit(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

    def run(self):
        self.log("正在初始化客户端...")
        if not self.client.login():
            self.log("登录失败，请检查 Cookie 或重新扫码")
            self.finished_signal.emit(False, "登录失败")
            return

        self.log(f"登录成功: {self.config.get('member_name', '未知用户')}")
        
        # 1. 等待时间
        start_time_str = self.config.get('start_time')
        if start_time_str:
            try:
                target_time = datetime.datetime.strptime(start_time_str, "%H:%M:%S")
                now = datetime.datetime.now()
                target_time = now.replace(hour=target_time.hour, minute=target_time.minute, second=target_time.second)
                
                if target_time > now:
                    wait_sec = (target_time - now).total_seconds()
                    self.log(f"等待到 {start_time_str} 开始 (约 {wait_sec:.0f} 秒)...")
                    while self.is_running and datetime.datetime.now() < target_time:
                        time.sleep(0.5)
                    
                    if not self.is_running: return
                    self.log("时间到，开始抢号！")
            except ValueError:
                self.log("时间格式错误，忽略等待")

        # 2. 循环抢号
        unit_id = self.config['unit_id']
        dep_id = self.config['dep_id']
        target_dates = self.config.get('target_dates', [])
        member_id = self.config.get('member_id')
        
        retry_interval = float(self.config.get('retry_interval', 0.5))
        max_retries = int(self.config.get('max_retries', 0))
        attempt = 0

        while self.is_running:
            attempt += 1
            if max_retries > 0 and attempt > max_retries:
                self.log("达到最大重试次数，停止")
                self.finished_signal.emit(False, "超时未抢到")
                break

            self.log(f"第 {attempt} 次尝试扫描...")
            
            try:
                # 遍历日期
                found_ticket = False
                for date_str in target_dates:
                    if not self.is_running: break
                    
                    # self.log(f"查询 {date_str}...") # 日志太多可注释
                    docs = self.client.get_schedule(unit_id, dep_id, date_str)
                    
                    if not docs: continue

                    # 简化逻辑：只找有号的如果不挑医生
                    # 这里暂不实现复杂的筛选逻辑复刻，先做通用的
                    available_docs = [d for d in docs if d.get('schedules')]
                    for doc in available_docs:
                         # 这里简单粗暴：有号就抢第一个
                         # 实际应从 config 读取 filtered doctors
                         # 假设 config['doctor_ids'] 为空则全抢
                         
                         target_doc_ids = self.config.get('doctor_ids', [])
                         if target_doc_ids and str(doc['doctor_id']) not in target_doc_ids:
                             continue

                         for sch in doc['schedules']:
                             if int(str(sch.get('left_num', 0))) > 0:
                                 self.log(f"发现号源: {date_str} {doc['doctor_name']} {sch['time_type_desc']}")
                                 
                                 # 尝试锁单/获取详情
                                 sch_id = sch['schedule_id']
                                 detail = self.client.get_ticket_detail(unit_id, dep_id, sch_id)
                                 
                                 if not detail: continue
                                 
                                 # 提交
                                 times = detail.get('times') or detail.get('time_slots')
                                 if not times: continue
                                 
                                 selected_time = times[0] # 默认第一个
                                 
                                 # 构造提交参数
                                 res = self.client.submit_order(
                                     unit_id=unit_id,
                                     dep_id=dep_id,
                                     schedule_id=sch_id,
                                     time_type=sch['time_type'],
                                     doctor_id=doc['doctor_id'],
                                     his_doc_id=doc['his_doc_id'],
                                     detlid=selected_time['value'],
                                     detl_name=selected_time['name'],
                                     member_id=member_id,
                                     sch_data=detail.get('sch_data'),
                                     detlid_realtime=detail.get('detlid_realtime'),
                                     level_code=detail.get('level_code'),
                                     sch_date=sch.get('to_date', date_str)
                                 )
                                 
                                 if res and (res.get('success') or res.get('status')):
                                     self.log(f"SUCCESS: 抢号成功! {res.get('msg', '')}")
                                     self.finished_signal.emit(True, "抢号成功")
                                     return
                                 else:
                                     self.log(f"FAILED: {res.get('msg')}")

            except Exception as e:
                self.log(f"ERROR: {e}")

            if not self.is_running: break
            time.sleep(retry_interval)

    def stop(self):
        self.is_running = False

class ResourceLoader(QThread):
    data_loaded = pyqtSignal(str, object) # key, data

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.tasks = [] # (key, args)
        self.is_running = True

    def fetch(self, key, *args):
        self.tasks.append((key, args))
        if not self.isRunning():
            self.start()

    def run(self):
        while self.is_running and self.tasks:
            try:
                if not self.tasks: break
                key, args = self.tasks.pop(0)
                
                data = None
                if key == 'hospitals':
                    # args[0] is city_id
                    data = self.client.get_hospitals_by_city(args[0])
                elif key == 'deps':
                    # args[0] is unit_id
                    data = self.client.get_deps_by_unit(args[0])
                elif key == 'doctors':
                    # unit_id, dep_id, date
                    data = self.client.get_schedule(args[0], args[1], args[2])
                elif key == 'doctors_forecast':
                    # unit_id, dep_id, start_date_str
                    # 预测模式：扫描未来7天，汇总是该科室的出诊医生
                    uid, did, start_date = args[0], args[1], args[2]
                    all_docs = {}
                    try:
                        dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                        for i in range(7):
                            curr = (dt + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                            docs = self.client.get_schedule(uid, did, curr)
                            if docs:
                                for d in docs:
                                    did_val = str(d.get('doctor_id'))
                                    if did_val not in all_docs:
                                        d['source_date'] = curr # 记录最早来源日期
                                        all_docs[did_val] = d
                            time.sleep(0.2) # 避免请求过快
                    except Exception as e:
                        print(f"Forecast error: {e}")
                    data = list(all_docs.values())
                
                self.data_loaded.emit(key, data)
            except Exception as e:
                print(f"Loader Error ({key}): {e}")
                self.data_loaded.emit(key, [])
            
            # Small delay to yield
            self.msleep(50)
    
    def stop(self):
        self.is_running = False
        self.wait()
