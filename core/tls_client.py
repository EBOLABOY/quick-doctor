#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TLS 指纹伪造客户端 - 使用 curl_cffi 模拟真实浏览器
绕过 Cloudflare/阿里云 WAF 的 TLS 指纹检测
"""
import json
import os
import time
import hashlib
import random
import string
import re
from urllib.parse import urljoin, unquote
from datetime import datetime
from typing import List, Dict, Optional, Any

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    print("[!] curl_cffi 未安装，TLS 指纹伪造不可用")
    print("[!] 安装命令: pip install curl_cffi")

from bs4 import BeautifulSoup


class TLSHealthClient:
    """
    TLS 指纹伪造客户端
    
    使用 curl_cffi 模拟 Chrome/Safari 的真实 TLS 握手特征
    可绕过基于 JA3 指纹的 WAF 检测
    """
    
    # 支持的浏览器指纹
    IMPERSONATE_OPTIONS = [
        "chrome120",
        "chrome119", 
        "chrome110",
        "safari17_0",
        "safari15_5",
        "edge101"
    ]
    
    def __init__(self, impersonate: str = "chrome120"):
        """
        初始化 TLS 客户端
        
        Args:
            impersonate: 模拟的浏览器类型，默认 chrome120
        """
        if not CURL_CFFI_AVAILABLE:
            raise ImportError("curl_cffi 未安装，请运行: pip install curl_cffi")
        
        self.impersonate = impersonate
        self.session = curl_requests.Session(impersonate=impersonate)
        
        # 使用脚本所在目录
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cookie_file = os.path.join(self.script_dir, 'cookies.json')
        
        self.headers = {
            'User-Agent': self._get_ua_for_impersonate(),
            'Referer': 'https://www.91160.com/',
            'Origin': 'https://www.91160.com',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        self.session.headers.update(self.headers)
        
        self.access_hash = None
        
        if self.load_cookies():
            print(f"[+] TLS客户端初始化成功 (指纹: {impersonate})")
    
    def _get_ua_for_impersonate(self) -> str:
        """根据模拟类型返回匹配的 User-Agent"""
        ua_map = {
            "chrome120": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "chrome119": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "chrome110": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "safari17_0": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "safari15_5": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
            "edge101": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.53",
        }
        return ua_map.get(self.impersonate, ua_map["chrome120"])
    
    def load_cookies(self) -> bool:
        """加载本地 Cookie"""
        if not os.path.exists(self.cookie_file):
            return False
        
        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                cookies_list = json.load(f)
            
            if isinstance(cookies_list, list):
                for cookie in cookies_list:
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    self.session.cookies.set(name, value)
                    if name == 'access_hash':
                        self.access_hash = value
            else:
                for name, value in cookies_list.items():
                    self.session.cookies.set(name, value)
                self.access_hash = cookies_list.get('access_hash')
            
            return True
        except Exception as e:
            print(f"[-] 加载 Cookie 失败: {e}")
            return False
    
    def check_login(self) -> bool:
        """检查登录状态"""
        if not self.access_hash:
            return False
        
        try:
            r = self.session.get(
                "https://user.91160.com/user/index.html",
                allow_redirects=False,
                timeout=10
            )
            return r.status_code == 200
        except Exception:
            return False
    
    def get_hospitals_by_city(self, city_id: str = "5") -> List[Dict]:
        """获取医院列表"""
        url = "https://www.91160.com/ajax/getunitbycity.html"
        try:
            r = self.session.post(url, data={"c": city_id})
            return r.json()
        except:
            return []
    
    def get_deps_by_unit(self, unit_id: str) -> List[Dict]:
        """获取科室列表"""
        url = "https://www.91160.com/ajax/getdepbyunit.html"
        try:
            r = self.session.post(url, data={"keyValue": unit_id})
            return r.json()
        except:
            return []
    
    def get_members(self) -> List[Dict]:
        """获取就诊人列表"""
        url = "https://user.91160.com/member.html"
        try:
            r = self.session.get(url)
            
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
                    is_certified = any("认证" in td.text for td in tds)
                    members.append({
                        'id': mid,
                        'name': name,
                        'certified': is_certified
                    })
            
            return members
        except Exception as e:
            print(f"[-] 获取就诊人失败: {e}")
            return []
    
    def get_schedule(self, unit_id: str, dep_id: str, date: str = None) -> List[Dict]:
        """获取排班信息"""
        if not date:
            date = time.strftime("%Y-%m-%d")
        
        url = "https://gate.91160.com/guahao/v1/pc/sch/dep"
        
        if not self.access_hash:
            print("[-] 没有 access_hash")
            return []
        
        params = {
            "unit_id": unit_id,
            "dep_id": dep_id,
            "date": date,
            "p": 0,
            "user_key": self.access_hash
        }
        
        try:
            r = self.session.get(url, params=params)
            data = r.json()
            
            if str(data.get('result_code')) != '1':
                return []
            
            result_data = data.get('data', {})
            doc_list = result_data.get('doc', [])
            sch_data_map = result_data.get('sch', {})
            
            valid_docs = []
            for doc in doc_list:
                doc_id = str(doc.get('doctor_id'))
                sch_map = sch_data_map.get(doc_id)
                
                if not sch_map:
                    continue
                
                schedules = []
                for time_type in ['am', 'pm']:
                    type_data = sch_map.get(time_type, {})
                    if isinstance(type_data, dict):
                        for _, slot in type_data.items():
                            if slot.get('schedule_id'):
                                schedules.append(slot)
                    elif isinstance(type_data, list):
                        for slot in type_data:
                            if slot.get('schedule_id'):
                                schedules.append(slot)
                
                if schedules:
                    doc['schedules'] = schedules
                    doc['schedule_id'] = schedules[0]['schedule_id']
                    total_left = sum(int(s.get('left_num', 0)) for s in schedules 
                                    if str(s.get('left_num')).isdigit())
                    doc['total_left_num'] = total_left
                    valid_docs.append(doc)
            
            return valid_docs
            
        except Exception as e:
            print(f"[-] 排班查询失败: {e}")
            return []
    
    def get_ticket_detail(
        self, unit_id: str, dep_id: str, sch_id: str, member_id: Optional[str] = None
    ) -> Optional[Dict]:
        """获取号源详情"""
        url = f"https://www.91160.com/guahao/ystep1/uid-{unit_id}/depid-{dep_id}/schid-{sch_id}.html"
        
        try:
            r = self.session.get(url)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            delts_div = soup.find(id='delts')
            time_slots = []
            if delts_div:
                for li in delts_div.find_all('li'):
                    text = li.get_text(strip=True)
                    val = li.get('val')
                    if val:
                        time_slots.append({'name': text, 'value': val})
            
            sch_data = soup.find('input', {'name': 'sch_data'})
            detlid_realtime = soup.find(id='detlid_realtime')
            level_code = soup.find(id='level_code')
            sch_date = soup.find("input", {"name": "sch_date"}) or soup.find(id="sch_date")
            order_no = soup.find("input", {"name": "order_no"}) or soup.find(id="order_no")
            disease_content = soup.find("input", {"name": "disease_content"}) or soup.find(id="disease_content")
            is_hot = soup.find("input", {"name": "is_hot"}) or soup.find(id="is_hot")
            his_mem_id = soup.find("input", {"name": "hisMemId"}) or soup.find(id="hismemid")
            disease_input = soup.find("textarea", {"name": "disease_input"}) or soup.find(id="disease_input")

            def _node_value(node) -> str:
                if not node:
                    return ""
                return (node.get("value") or "").strip()

            def _textarea_value(node) -> str:
                if not node:
                    return ""
                return (node.get_text() or "").strip()

            def _normalize_address_id(value: str) -> str:
                value = (value or "").strip()
                if not value or value in ("0", "-1"):
                    return ""
                return value

            def _normalize_address_text(text: str) -> str:
                text = (text or "").strip()
                if not text:
                    return ""
                placeholders = ("请选择", "请填写", "请输入", "城市地址")
                if any(p in text for p in placeholders):
                    return ""
                return text

            address_id = ""
            address_text = ""
            address_list = []

            mid_value = str(member_id).strip() if member_id is not None else ""
            mid_inputs = soup.find_all("input", {"name": "mid"})
            selected_mid = None
            mid_address_id = ""
            mid_address_text = ""
            if mid_value:
                for item in mid_inputs:
                    if (item.get("value") or "").strip() == mid_value:
                        selected_mid = item
                        break
            else:
                for item in mid_inputs:
                    if item.has_attr("checked"):
                        selected_mid = item
                        break
                if selected_mid is None and mid_inputs:
                    selected_mid = mid_inputs[0]

            if selected_mid is not None:
                mid_address_id = _normalize_address_id(
                    selected_mid.get("area_id")
                    or selected_mid.get("areaId")
                    or selected_mid.get("areaid")
                    or ""
                )
                mid_address_text = _normalize_address_text(
                    selected_mid.get("address")
                    or selected_mid.get("addr")
                    or ""
                )
            address_input = (
                soup.find('input', {'name': 'addressId'})
                or soup.find('input', id='addressId')
            )
            if address_input:
                address_id = _normalize_address_id(address_input.get('value', ''))
            address_text_input = (
                soup.find('input', {'name': 'address'})
                or soup.find('input', id='address')
            )
            if address_text_input:
                address_text = _normalize_address_text(address_text_input.get('value', ''))

            address_select = (
                soup.find('select', {'name': 'addressId'})
                or soup.find('select', id='addressId')
                or soup.find('select', id='useraddress_area')
            )
            selected_address = None
            if address_select:
                for option in address_select.find_all('option'):
                    value = _normalize_address_id(option.get('value', ''))
                    text = _normalize_address_text(option.get_text(strip=True))
                    if not value or not text:
                        continue
                    item = {'id': value, 'text': text}
                    address_list.append(item)
                    if option.has_attr("selected") and selected_address is None:
                        selected_address = item

            if address_id and not address_text:
                for item in address_list:
                    if item.get("id") == address_id:
                        address_text = item.get("text", "")
                        break

            if not address_id or not address_text:
                chosen = selected_address or (address_list[0] if address_list else None)
                if chosen:
                    address_id = address_id or chosen.get("id", "")
                    address_text = address_text or chosen.get("text", "")

            if mid_address_id:
                address_id = mid_address_id
            if mid_address_text:
                address_text = mid_address_text
            
            return {
                'times': time_slots,
                'time_slots': time_slots,
                'sch_data': sch_data.get('value') if sch_data else '',
                'detlid_realtime': detlid_realtime.get('value') if detlid_realtime else '',
                'level_code': level_code.get('value') if level_code else '',
                'sch_date': _node_value(sch_date),
                'order_no': _node_value(order_no),
                'disease_content': _node_value(disease_content),
                'disease_input': _textarea_value(disease_input),
                'is_hot': _node_value(is_hot),
                'hisMemId': _node_value(his_mem_id),
                'addressId': address_id,
                'address': address_text,
                'addresses': address_list
            }
        except Exception as e:
            print(f"[-] 获取号源详情失败: {e}")
            return None
    
    def submit_order(self, params: Dict) -> Dict:
        """提交订单"""
        url = "https://www.91160.com/guahao/ysubmit.html"
        
        def _form_value(value):
            if value is None:
                return ""
            if isinstance(value, bool):
                return "1" if value else "0"
            return str(value)

        data = {
            "sch_data": _form_value(params.get("sch_data")),
            "mid": _form_value(params.get("member_id")),
            "addressId": _form_value(params.get("addressId", "")),
            "address": _form_value(params.get("address", "")),
            "hisMemId": _form_value(params.get("hisMemId", params.get("his_mem_id", ""))),
            "disease_input": _form_value(params.get("disease_input", "")),
            "order_no": _form_value(params.get("order_no", "")),
            "disease_content": _form_value(params.get("disease_content", "")),
            "accept": "1",
            "unit_id": _form_value(params.get("unit_id")),
            "schedule_id": _form_value(params.get("schedule_id")),
            "dep_id": _form_value(params.get("dep_id")),
            "his_dep_id": _form_value(params.get("his_dep_id", "")),
            "sch_date": _form_value(params.get("sch_date", "")),
            "time_type": _form_value(params.get("time_type", "")),
            "doctor_id": _form_value(params.get("doctor_id", "")),
            "his_doc_id": _form_value(params.get("his_doc_id", "")),
            "detlid": _form_value(params.get("detlid")),
            "detlid_realtime": _form_value(params.get("detlid_realtime")),
            "level_code": _form_value(params.get("level_code")),
            "is_hot": _form_value(params.get("is_hot", "")),
        }
        
        try:
            address_id = str(data.get("addressId") or "").strip()
            address_text = str(data.get("address") or "").strip()
            if (not address_id or address_id in ("0", "-1")) or not address_text:
                try:
                    ticket_detail = self.get_ticket_detail(
                        data.get("unit_id"),
                        data.get("dep_id"),
                        data.get("schedule_id"),
                        member_id=data.get("mid"),
                    )
                    if ticket_detail:
                        data["addressId"] = ticket_detail.get("addressId") or data.get("addressId")
                        data["address"] = ticket_detail.get("address") or data.get("address")
                        for key in ("hisMemId", "sch_date", "order_no", "disease_input", "disease_content", "is_hot"):
                            if str(data.get(key) or "").strip():
                                continue
                            value = ticket_detail.get(key)
                            if value is not None:
                                data[key] = value
                except Exception:
                    pass

            self._set_submit_cookies(data)

            headers = self._build_submit_headers(
                params.get("unit_id"),
                params.get("dep_id"),
                params.get("schedule_id"),
            )

            mid = data.get("mid")
            if mid:
                try:
                    check_headers = headers.copy()
                    check_headers.update({
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    })
                    self.session.post(
                        "https://www.91160.com/guahao/checkidinfo.html",
                        data={"mid": mid},
                        headers=check_headers,
                        timeout=5,
                    )
                except Exception:
                    pass
            r = self.session.post(url, data=data, headers=headers, allow_redirects=False)
            
            if r.status_code in [301, 302]:
                redirect_url = urljoin(url, r.headers.get('Location', ''))
                if 'success' in redirect_url:
                    return {'success': True, 'status': True, 'msg': 'OK', 'url': redirect_url}
                else:
                    reason = ""
                    debug_path = ""
                    try:
                        resp2 = self.session.get(
                            redirect_url,
                            headers=headers,
                            allow_redirects=True,
                            timeout=10,
                        )
                        content = resp2.content or b""
                        if content:
                            debug_path = self._dump_submit_response(content)
                        text = resp2.text or ""
                        if not text.strip() and content:
                            try:
                                text = content.decode(resp2.encoding or "utf-8", errors="ignore")
                            except Exception:
                                text = ""
                        reason = self._extract_submit_message(text)
                        mid = data.get("mid")
                        if not reason and mid:
                            try:
                                soup2 = BeautifulSoup(text, "html.parser")
                                mid_node = soup2.find("input", {"name": "mid", "value": str(mid)})
                                if mid_node:
                                    reason = (mid_node.get("data-title") or "").strip()
                                    if not reason:
                                        need_check = (mid_node.get("need_check") or "").strip()
                                        is_info_complete = (mid_node.get("is_info_complete") or "").strip()
                                        if need_check == "1":
                                            reason = "就诊人信息需审核/校验，暂不可预约"
                                        elif is_info_complete == "0":
                                            reason = "就诊人信息未完善，无法预约"
                            except Exception:
                                reason = ""
                        if not reason:
                            snippet = re.sub(r'[\x00-\x1f\x7f]+', ' ', text)
                            snippet = re.sub(r'\s+', ' ', snippet).strip()[:200]
                            reason = snippet
                    except Exception as e:
                        reason = f"跳转页面获取失败: {e}"

                    msg = f"提交异常跳转: {redirect_url}"
                    if reason:
                        msg = f"{msg} ({reason})"
                    if debug_path:
                        msg = f"{msg} Debug={debug_path}"
                    return {'success': False, 'status': False, 'msg': msg}

            content_type = r.headers.get('Content-Type', '')
            content_encoding = r.headers.get('Content-Encoding', '')
            content_length = len(r.content or b'')
            text = r.text or ""
            if not text.strip() and r.content:
                try:
                    text = r.content.decode(r.encoding or "utf-8", errors="ignore")
                except Exception:
                    text = ""
            msg = self._extract_submit_message(text)
            if msg:
                return {'success': False, 'status': False, 'msg': f'提交失败: {msg}'}
            snippet = re.sub(r'[\x00-\x1f\x7f]+', ' ', text)
            snippet = re.sub(r'\s+', ' ', snippet).strip()[:200]
            if snippet:
                return {'success': False, 'status': False, 'msg': f'提交失败 Code={r.status_code}, Resp={snippet}'}
            debug_path = self._dump_submit_response(r.content)
            return {
                'success': False,
                'status': False,
                'msg': (
                    "提交失败 "
                    f"Code={r.status_code}, "
                    f"Content-Type={content_type or '-'}, "
                    f"Content-Encoding={content_encoding or '-'}, "
                    f"Len={content_length}, "
                    f"Debug={debug_path}"
                ),
            }
        except Exception as e:
            return {'success': False, 'status': False, 'msg': str(e)}

    def _extract_submit_message(self, text: str) -> str:
        if not text:
            return ""
        patterns = [
            r'alert\(["\']([^"\']+)["\']\)',
            r'layer\.msg\(["\']([^"\']+)["\']\)',
            r'layer\.alert\(["\']([^"\']+)["\']\)',
            r'msg\(["\']([^"\']+)["\']\)',
            r'toast\(["\']([^"\']+)["\']\)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        try:
            soup = BeautifulSoup(text, 'html.parser')
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            return title
        except Exception:
            return ""

    def _extract_uid_from_cookie_value(self, value: str) -> str:
        if not value:
            return ""
        try:
            decoded = unquote(value)
            data = json.loads(decoded)
            uid = data.get("fid") or data.get("uid") or data.get("id")
            return str(uid) if uid else ""
        except Exception:
            return ""

    def _get_uid_from_cookies(self) -> str:
        for cookie in self.session.cookies:
            if cookie.name in ("User_datas", "UserName_datas"):
                uid = self._extract_uid_from_cookie_value(cookie.value)
                if uid:
                    return uid
        return ""

    def _set_submit_cookies(self, data: Dict) -> None:
        uid = str(data.get("uid") or "").strip() or self._get_uid_from_cookies()
        dep_id = str(data.get("dep_id") or "").strip()
        doc_id = str(data.get("doctor_id") or "").strip()
        if not uid or not dep_id or not doc_id:
            return

        member_id = str(data.get("mid") or "").strip()
        detlid = str(data.get("detlid") or "").strip()
        accept = str(data.get("accept") or "1").strip() or "1"
        cookies = {
            f"member_id_{uid}_{dep_id}_{doc_id}": member_id,
            f"detl_id_{uid}_{dep_id}_{doc_id}": detlid,
            f"accept_{uid}_{dep_id}_{doc_id}": accept,
        }
        for name, value in cookies.items():
            if not value:
                continue
            try:
                self.session.cookies.set(name, value, domain=".91160.com", path="/")
            except Exception:
                self.session.cookies.set(name, value)

    def _build_submit_headers(self, unit_id: str, dep_id: str, schedule_id: str) -> Dict:
        headers = self.headers.copy()
        if unit_id and dep_id and schedule_id:
            referer_url = (
                "https://www.91160.com/guahao/ystep1/"
                f"uid-{unit_id}/depid-{dep_id}/schid-{schedule_id}.html"
            )
            headers["Referer"] = referer_url
        headers["Origin"] = "https://www.91160.com"
        headers["Connection"] = "keep-alive"
        headers["Pragma"] = "no-cache"
        headers["Cache-Control"] = "no-cache"
        cookie_header = self._build_submit_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _build_submit_cookie_header(self) -> str:
        user_cookies = []
        www_cookies = []
        root_cookies = []
        for c in self.session.cookies:
            domain = (getattr(c, "domain", "") or "").lower()
            if "user.91160.com" in domain:
                user_cookies.append(c)
            elif "www.91160.com" in domain:
                www_cookies.append(c)
            elif domain.endswith("91160.com") or domain == "":
                root_cookies.append(c)
        parts = []
        seen = set()
        for cookie in user_cookies + www_cookies + root_cookies:
            name = cookie.name
            if name in seen:
                continue
            seen.add(name)
            parts.append(f"{name}={cookie.value}")
        return "; ".join(parts)

    def _dump_submit_response(self, content: bytes) -> str:
        logs_dir = os.path.join(self.script_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        filename = f"submit_resp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"
        path = os.path.join(logs_dir, filename)
        try:
            with open(path, "wb") as f:
                f.write(content or b"")
        except Exception:
            return path
        return path
    
    def get_server_datetime(self) -> Optional[datetime]:
        """获取服务器时间"""
        url = "https://www.91160.com/favicon.ico"
        try:
            r = self.session.get(url, timeout=5)
            date_header = r.headers.get('Date')
            if date_header:
                from email.utils import parsedate_to_datetime
                import datetime as dt
                server_dt = parsedate_to_datetime(date_header)
                if server_dt.tzinfo is None:
                    server_dt = server_dt.replace(tzinfo=dt.timezone.utc)
                return server_dt.astimezone()
        except:
            pass
        return None
    
    def rotate_fingerprint(self):
        """切换浏览器指纹（用于规避检测）"""
        new_impersonate = random.choice(self.IMPERSONATE_OPTIONS)
        self.impersonate = new_impersonate
        self.session = curl_requests.Session(impersonate=new_impersonate)
        self.session.headers.update(self.headers)
        self.headers['User-Agent'] = self._get_ua_for_impersonate()
        self.load_cookies()
        print(f"[*] 切换指纹: {new_impersonate}")


def test_tls_client():
    """测试 TLS 客户端"""
    print("=== TLS 指纹客户端测试 ===\n")
    
    try:
        client = TLSHealthClient(impersonate="chrome120")
    except ImportError as e:
        print(f"[-] {e}")
        return
    
    if client.check_login():
        print("[+] 登录状态: 有效")
        members = client.get_members()
        print(f"[+] 就诊人: {len(members)} 位")
    else:
        print("[-] 登录状态: 无效，请重新扫码登录")


if __name__ == "__main__":
    test_tls_client()
