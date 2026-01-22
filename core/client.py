import requests
import json
import time
import os
import hashlib
import random
import string
import datetime
from email.utils import parsedate_to_datetime
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

class HealthClient:
    def __init__(self):
        self.session = requests.Session()
        try:
            self.ua = UserAgent()
            ua_value = self.ua.random
        except Exception:
            self.ua = None
            ua_value = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.headers = {
            'User-Agent': ua_value,
            'Referer': 'https://www.91160.com/',
            'Origin': 'https://www.91160.com'
        }
        self.session.headers.update(self.headers)
        self.cookie_file = 'cookies.json'
        
        if self.load_cookies():
            print("[+] 本地 Cookie 加载成功")

    def load_cookies(self):
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    cookies_list = json.load(f)
                    # 兼容 List 和 Dict 格式
                    if isinstance(cookies_list, list):
                        for cookie in cookies_list:
                            self.session.cookies.set(
                                cookie['name'], 
                                cookie['value'], 
                                domain=cookie.get('domain', '.91160.com'),
                                path=cookie.get('path', '/')
                            )
                    else:
                        self.session.cookies.update(cookies_list)
                return True
            except Exception as e:
                print(f"[-] 加载 Cookie 异常: {e}")
                return False
        return False

    def save_cookies_from_browser(self, browser_cookies):
        """保存浏览器 Cookie 到本地（保留完整信息）"""
        with open(self.cookie_file, 'w', encoding='utf-8') as f:
            json.dump(browser_cookies, f)
        
        # 同时更新当前 Session
        for cookie in browser_cookies:
            self.session.cookies.set(
                cookie['name'], 
                cookie['value'], 
                domain=cookie.get('domain', '.91160.com'),
                path=cookie.get('path', '/')
            )
        print(f"[+] 完整 Cookie ({len(browser_cookies)}个) 已保存")

    def check_login(self):
        """检查登录状态"""
        # 1. 检查是否存在 access_hash
        has_hash = False
        for c in self.session.cookies:
            if c.name == 'access_hash':
                has_hash = True
                break
        if not has_hash:
            return False
        
        # 2. 实测接口: 获取用户信息 (需要登录)
        # 用 user/index.html 检查，如果不登录会跳回登录页
        try:
            # allow_redirects=False, 如果返回 302 说明未登录
            r = self.session.get("https://user.91160.com/user/index.html", allow_redirects=False, timeout=5)
            if r.status_code == 200:
                return True
            return False
        except:
            return False

    def login_with_browser(self):
        """Playwright 扫码登录"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[-] 未安装 playwright")
            return False

        print("[*] 启动浏览器...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                
                # 1. 构造微信扫码 URL
                state = hashlib.md5(''.join(random.choices(string.ascii_letters + string.digits, k=16)).encode()).hexdigest()
                url = f"https://open.weixin.qq.com/connect/qrconnect?appid=wxdfec0615563d691d&redirect_uri=http%3A%2F%2Fuser.91160.com%2Fsupplier-wechat.html&response_type=code&scope=snsapi_login&state={state}"
                
                page.goto(url)
                print("[*] 请扫码登录...")
                
                # 2. 等待登录成功 (回到 91160)
                try:
                    page.wait_for_url(lambda u: "91160.com" in u and "weixin" not in u, timeout=300000)
                except:
                    print("[-] 扫码超时")
                    browser.close()
                    return False
                
                print("[+] 扫码成功，正在初始化环境...")
                
                # 3. 关键：访问各个子域以确保 Cookie 完整
                page.goto("https://www.91160.com/")
                # time.sleep(1)
                page.goto("https://user.91160.com/user/index.html")
                # time.sleep(1)
                # 访问 gate 确保 API 权限 (虽然 gate 是 API 域，通常不做页面展示，但访问一下根绝无坏处)
                # 实际上 gate 可能没有页面，但可以访问一个 404 页
                
                # 4. 提取 Cookie
                cookies = context.cookies()
                print(f"[*] 提取到 {len(cookies)} 个 Cookie")
                
                self.save_cookies_from_browser(cookies)
                browser.close()
                return True

        except Exception as e:
            print(f"[-] 浏览器登录失败: {e}")
            return False

    def login(self):
        # 先尝试加载本地 Cookie
        self.load_cookies()
        
        if self.check_login():
            print("[+] Cookie 验证成功")
            return True
        
        print("[*] Cookie 已失效或未登录，启动浏览器扫码...")
        return self.login_with_browser()

    # ============ API 接口 ============
    
    def get_hospitals_by_city(self, city_id="5"):
        url = "https://www.91160.com/ajax/getunitbycity.html"
        data = {"c": city_id}
        try:
            r = self.session.post(url, data=data)
            return r.json()
        except: return []

    def get_deps_by_unit(self, unit_id):
        url = "https://www.91160.com/ajax/getdepbyunit.html"
        data = {"keyValue": unit_id}
        try:
            r = self.session.post(url, data=data)
            return r.json()
        except: return []

    def get_members(self):
        """获取就诊人列表"""
        url = "https://user.91160.com/member.html"
        try:
            r = self.session.get(url)
            r.encoding = 'utf-8'  # 强制 UTF-8
            
            # 调试：检查是否需要登录
            if 'login' in r.url.lower() or '登录' in r.text[:500]:
                print("[-] 获取就诊人失败: 需要重新登录")
                return []
            
            soup = BeautifulSoup(r.text, 'html.parser')
            tbody = soup.find('tbody', {'id': 'mem_list'})
            members = []
            if tbody:
                for tr in tbody.find_all('tr'):
                    mid = tr.get('id', '').replace('mem', '')
                    tds = tr.find_all('td')
                    if not tds:
                        continue
                    name = tds[0].get_text(strip=True).replace('默认', '')
                    # 检查是否认证
                    is_certified = any("认证" in td.text for td in tds)
                    members.append({
                        'id': mid,
                        'name': name,
                        'certified': is_certified
                    })
            else:
                print("[-] 未找到就诊人列表 (mem_list)")
            return members
        except Exception as e:
            print(f"[-] 获取就诊人失败: {e}")
            return []

    def get_ticket_detail(self, unit_id, dep_id, sch_id):
        """获取具体的号源时间段和下单所需的隐藏参数"""
        url = f"https://www.91160.com/guahao/ystep1/uid-{unit_id}/depid-{dep_id}/schid-{sch_id}.html"
        try:
            r = self.session.get(url)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # 1. 提取时间段
            delts_div = soup.find(id='delts')
            time_slots = []
            if delts_div:
                for li in delts_div.find_all('li'):
                    text = li.get_text(strip=True)
                    val = li.get('val')
                    if val:
                        time_slots.append({'name': text, 'value': val})
            
            # 2. 提取隐藏参数
            sch_data = soup.find('input', {'name': 'sch_data'})
            detlid_realtime = soup.find(id='detlid_realtime')
            level_code = soup.find(id='level_code')
            
            result = {
                'times': time_slots,
                'time_slots': time_slots,
                'sch_data': sch_data.get('value') if sch_data else '',
                'detlid_realtime': detlid_realtime.get('value') if detlid_realtime else '',
                'level_code': level_code.get('value') if level_code else ''
            }
            return result
        except Exception as e:
            print(f"[-] 获取号源详情失败: {e}")
            return None

    def submit_order(self, order_params=None, **kwargs):
        """提交订单"""
        url = "https://www.91160.com/guahao/ysubmit.html"
        # 兼容旧的单参数传入方式
        if order_params is None:
            params = kwargs.get('order_params', kwargs)
        else:
            params = order_params
        
        data = {
            'sch_data': params.get('sch_data'),
            'mid': params.get('member_id'),
            'addressId': params.get('addressId', '3317'),
            'address': params.get('address', 'Civic Center'),
            'disease_input': params.get('disease_input', '自动抢号'),
            'order_no': '',
            'disease_content': params.get('disease_content', '自动抢号'),
            'accept': '1',
            'unit_id': params.get('unit_id'),
            'schedule_id': params.get('schedule_id'),
            'dep_id': params.get('dep_id'),
            'his_dep_id': params.get('his_dep_id', ''),
            'sch_date': params.get('sch_date', params.get('to_date', '')),
            'time_type': params.get('time_type', ''),
            'doctor_id': params.get('doctor_id', ''),
            'his_doc_id': params.get('his_doc_id', ''),
            'detlid': params.get('detlid'),
            'detlid_realtime': params.get('detlid_realtime'),
            'level_code': params.get('level_code'),
            'is_hot': '',
            'pay_online': '0',
            'detl_name': params.get('detl_name', ''),
            'to_date': params.get('to_date', params.get('sch_date', '')),
            'his_mem_id': ''
        }
        
        try:
            r = self.session.post(url, data=data, allow_redirects=False)
            if r.status_code in [301, 302] and 'Location' in r.headers:
                redirect_url = r.headers['Location']
                # 如果跳转到 success 页面，说明成功
                if "success" in redirect_url:
                    return {'success': True, 'status': True, 'msg': 'OK', 'url': redirect_url}
                else:
                    return {'success': False, 'status': False, 'msg': f'提交异常跳转: {redirect_url}'}
            else:
                return {'success': False, 'status': False, 'msg': f'提交失败 Code={r.status_code}, Resp={r.text[:200]}' }
        except Exception as e:
            return {'success': False, 'status': False, 'msg': str(e)}

    def get_server_datetime(self):
        """获取服务器时间（用于定时抢号校准）"""
        url = "https://www.91160.com/favicon.ico"
        try:
            r = self.session.get(url, timeout=5)
            date_header = r.headers.get('Date')
            if not date_header:
                return None
            dt = parsedate_to_datetime(date_header)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone()
        except Exception:
            return None

    def get_schedule(self, unit_id, dep_id, date=None):
        if not date: date = time.strftime("%Y-%m-%d")
        url = "https://gate.91160.com/guahao/v1/pc/sch/dep"
        
        # 自动提取唯一的 access_hash (如果有多个，取最新的)
        # requests.cookies 是 CookieJar，迭代它
        user_keys = []
        for c in self.session.cookies:
            if c.name == 'access_hash':
                user_keys.append(c.value)
        user_keys = list(set(user_keys))
        
        if not user_keys:
            print("[-] 没有 access_hash")
            return []

        # 尝试所有 key
        for key in user_keys:
            params = {
                "unit_id": unit_id,
                "dep_id": dep_id,
                "date": date,
                "p": 0,
                "user_key": key
            }
            # Gate 接口通常需要 Origin
            headers = self.headers.copy()
            headers['Origin'] = 'https://www.91160.com'
            headers['Referer'] = 'https://www.91160.com/'
            
            try:
                r = self.session.get(url, params=params, headers=headers)
                data = r.json()
                # print(f"[DEBUG] Try Key {key[:5]}... Code={data.get('result_code')}")
                
                if str(data.get('result_code')) == '1':
                    result_data = data.get('data', {})
                    doc_list = result_data.get('doc', [])
                    
                    # 调试：打印 result_data 的 keys
                    # print(f"[DEBUG] Keys in result_data: {list(result_data.keys())[:20]}")
                    
                    sch_data_map = result_data.get('sch', {})

                    # 遍历医生列表，填充排班信息
                    valid_docs = []
                    for doc in doc_list:
                        doc_id = str(doc.get('doctor_id'))
                        # 排班数据在 data['sch'][doc_id] 中
                        sch_map = sch_data_map.get(doc_id)
                        
                        if not sch_map: 
                             # print(f"[DEBUG] No sch_map for {doc_id}")
                             continue
                        
                        # 提取所有时段 (AM/PM)
                        schedules = []
                        for time_type in ['am', 'pm']:
                            type_data = sch_map.get(time_type, {})
                            # type_data 可能是 list (空时) 或 dict (有排班时)
                            if isinstance(type_data, dict):
                                for _, slot in type_data.items():
                                    # 必须有 schedule_id 且未约满 (y_state != 1 且 left_num > 0)
                                    # 注意: 有些情况 left_num=0 但 y_state_desc="可预约"，需综合判断
                                    # 这里先不过滤，全部拿回来让 main.py 决定如何显示
                                    if slot.get('schedule_id'):
                                        schedules.append(slot)
                            elif isinstance(type_data, list):
                                for slot in type_data:
                                    if slot.get('schedule_id'):
                                        schedules.append(slot)

                        if schedules:
                            doc['schedules'] = schedules
                            # 把第一个有效的 schedule_id 放到顶层以便兼容旧代码 (可选)
                            doc['schedule_id'] = schedules[0]['schedule_id']
                            doc['time_type_desc'] = schedules[0].get('time_type_desc', '')
                            # 计算总余号
                            total_left = sum(int(s.get('left_num', 0)) for s in schedules if str(s.get('left_num')).isdigit())
                            doc['total_left_num'] = total_left
                            valid_docs.append(doc)
                    
                    if valid_docs:
                        return valid_docs
                    
                    # 如果没有有效排班的医生，尝试继续(虽然后续key可能也一样)或直接返回空
                    # 但考虑到可能有缓存或Key差异，继续尝试下一个Key也没问题，
                    # 不过通常一个Key能拿到数据，其他Key拿到的也一样。
                    # 这里如果拿到doc_list但没拼出schedules，说明真没号。
                    if doc_list and not valid_docs:
                         print("[-] 获取到医生列表但无具体排班信息")
                         return []

                elif str(data.get('error_code')) == '10022':
                    continue # 尝试下一个
            except Exception as e:
                print(f"[-] API Exception: {e}")
        
        print(f"[-] 排班查询失败 (Keys tested: {len(user_keys)})")
        return []
