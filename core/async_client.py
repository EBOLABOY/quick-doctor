#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
异步高并发 HTTP 客户端 - 基于 httpx
支持并发查询多个日期/医生的排班信息
"""
import httpx
import asyncio
import json
import os
import time
import re
from urllib.parse import urljoin, unquote
from datetime import datetime
from typing import List, Dict, Optional, Any


class AsyncHealthClient:
    """异步高并发健康160客户端"""
    
    BASE_URL = "https://www.91160.com"
    GATE_URL = "https://gate.91160.com"
    
    def __init__(self, max_concurrency: int = 10):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.cookies = httpx.Cookies()
        self.access_hash = None
        self._client: Optional[httpx.AsyncClient] = None
        
        # 使用脚本所在目录的绝对路径
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cookie_file = os.path.join(self.script_dir, 'cookies.json')
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.91160.com/',
            'Origin': 'https://www.91160.com'
        }
    
    async def load_cookies(self) -> bool:
        """加载本地 Cookie"""
        if not os.path.exists(self.cookie_file):
            return False
        
        try:
            if self._client is not None and not self._client.is_closed:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = None

            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                cookies_list = json.load(f)
            
            self.cookies = httpx.Cookies()
            self.access_hash = None
            if isinstance(cookies_list, list):
                for cookie in cookies_list:
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    if not name:
                        continue
                    domain = cookie.get("domain")
                    path = cookie.get("path") or "/"
                    try:
                        if domain:
                            self.cookies.set(name, value, domain=domain, path=path)
                        else:
                            self.cookies.set(name, value, path=path)
                    except Exception:
                        self.cookies.set(name, value)
                    if name == 'access_hash':
                        self.access_hash = value
            else:
                for name, value in (cookies_list or {}).items():
                    try:
                        self.cookies.set(name, value)
                    except Exception:
                        self.cookies.set(name, value)
                    if name == 'access_hash':
                        self.access_hash = value
            
            print(f"[+] 异步客户端: 加载了 {len(self.cookies)} 个 Cookie")
            return True
        except Exception as e:
            print(f"[-] 加载 Cookie 失败: {e}")
            return False
    
    def _get_client(self) -> httpx.AsyncClient:
        """创建带 Cookie 的异步客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                cookies=self.cookies,
                headers=self.headers,
                timeout=10.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
    
    async def get_schedule(self, unit_id: str, dep_id: str, date: str) -> List[Dict]:
        """获取单个日期的排班（带并发限制）"""
        async with self.semaphore:
            return await self._get_schedule_impl(unit_id, dep_id, date)
    
    async def _get_schedule_impl(self, unit_id: str, dep_id: str, date: str) -> List[Dict]:
        """排班查询实现"""
        url = f"{self.GATE_URL}/guahao/v1/pc/sch/dep"
        
        if not self.access_hash:
            self.access_hash = self._get_cookie_value("access_hash")
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
            client = self._get_client()
            resp = await client.get(url, params=params)
            data = resp.json()

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
                                slot['query_date'] = date
                                schedules.append(slot)
                    elif isinstance(type_data, list):
                        for slot in type_data:
                            if slot.get('schedule_id'):
                                slot['query_date'] = date
                                schedules.append(slot)

                if schedules:
                    doc['schedules'] = schedules
                    doc['schedule_id'] = schedules[0]['schedule_id']
                    doc['query_date'] = date
                    total_left = sum(int(s.get('left_num', 0)) for s in schedules
                                     if str(s.get('left_num')).isdigit())
                    doc['total_left_num'] = total_left
                    valid_docs.append(doc)

            return valid_docs

        except Exception as e:
            print(f"[-] 查询 {date} 排班失败: {e}")
            return []
    
    async def get_schedule_batch(self, unit_id: str, dep_id: str, dates: List[str]) -> List[Dict]:
        """并发查询多个日期的排班"""
        tasks = [self.get_schedule(unit_id, dep_id, d) for d in dates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_docs = []
        for result in results:
            if isinstance(result, list):
                all_docs.extend(result)
            elif isinstance(result, Exception):
                print(f"[-] 批量查询异常: {result}")
        
        return all_docs
    
    async def get_ticket_detail(
        self, unit_id: str, dep_id: str, sch_id: str, member_id: Optional[str] = None
    ) -> Optional[Dict]:
        """获取号源详情"""
        url = f"{self.BASE_URL}/guahao/ystep1/uid-{unit_id}/depid-{dep_id}/schid-{sch_id}.html"
        
        try:
            client = self._get_client()
            resp = await client.get(url)
            html = resp.text

            # 简化解析（生产环境建议用 BeautifulSoup）
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # 提取时间段
            delts_div = soup.find(id='delts')
            time_slots = []
            if delts_div:
                for li in delts_div.find_all('li'):
                    text = li.get_text(strip=True)
                    val = li.get('val')
                    if val:
                        time_slots.append({'name': text, 'value': val})

            # 提取隐藏参数
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
    
    async def submit_order(self, params: Dict) -> Dict:
        """异步提交订单"""
        url = f"{self.BASE_URL}/guahao/ysubmit.html"
        
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
            client = self._get_client()
            address_id = str(data.get("addressId") or "").strip()
            address_text = str(data.get("address") or "").strip()
            if (not address_id or address_id in ("0", "-1")) or not address_text:
                try:
                    ticket_detail = await self.get_ticket_detail(
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

            self._set_submit_cookies(client, data)

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
                    await client.post(
                        "https://www.91160.com/guahao/checkidinfo.html",
                        data={"mid": mid},
                        headers=check_headers,
                        timeout=5,
                    )
                except Exception:
                    pass

            resp = await client.post(url, data=data, headers=headers, follow_redirects=False)

            if resp.status_code in [301, 302]:
                redirect_url = urljoin(url, resp.headers.get('Location', ''))
                if 'success' in redirect_url:
                    return {'success': True, 'status': True, 'msg': 'OK', 'url': redirect_url}

                reason = ""
                debug_path = ""
                try:
                    resp2 = await client.get(redirect_url, headers=headers, follow_redirects=True)
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
                            from bs4 import BeautifulSoup
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

            content_type = resp.headers.get('Content-Type', '')
            content_encoding = resp.headers.get('Content-Encoding', '')
            content_length = len(resp.content or b'')
            text = resp.text or ""
            if not text.strip() and resp.content:
                try:
                    text = resp.content.decode(resp.encoding or "utf-8", errors="ignore")
                except Exception:
                    text = ""
            msg = self._extract_submit_message(text)
            if msg:
                return {'success': False, 'status': False, 'msg': f'提交失败: {msg}'}
            snippet = re.sub(r'[\x00-\x1f\x7f]+', ' ', text)
            snippet = re.sub(r'\s+', ' ', snippet).strip()[:200]
            if snippet:
                return {'success': False, 'status': False, 'msg': f'提交失败 Code={resp.status_code}, Resp={snippet}'}
            debug_path = self._dump_submit_response(resp.content)
            return {
                'success': False,
                'status': False,
                'msg': (
                    "提交失败 "
                    f"Code={resp.status_code}, "
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
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, 'html.parser')
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            return title
        except Exception:
            return ""

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

    def _get_cookie_value(self, name: str) -> str:
        if not name:
            return ""
        try:
            value = self.cookies.get(name)
        except Exception:
            value = ""
        if value:
            return str(value)
        jar = getattr(self.cookies, "jar", None)
        if jar:
            for cookie in jar:
                if cookie.name == name:
                    return cookie.value
        return ""

    def _set_cookie_value(self, name: str, value: str) -> None:
        if not name:
            return
        try:
            self.cookies.set(name, value, domain=".91160.com", path="/")
        except Exception:
            self.cookies.set(name, value)

    def _get_uid_from_cookies(self) -> str:
        for name in ("User_datas", "UserName_datas"):
            uid = self._extract_uid_from_cookie_value(self._get_cookie_value(name))
            if uid:
                return uid
        return ""

    def _set_submit_cookies(self, client: httpx.AsyncClient, data: Dict) -> None:
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
            self._set_cookie_value(name, value)
            try:
                client.cookies.set(name, value, domain=".91160.com", path="/")
            except Exception:
                client.cookies.set(name, value)

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
        return headers
    
    async def get_server_time(self) -> Optional[datetime]:
        """获取服务器时间（用于时间校准）"""
        url = f"{self.BASE_URL}/favicon.ico"
        
        try:
            client = self._get_client()
            resp = await client.get(url)
            date_header = resp.headers.get('Date')
            
            if date_header:
                from email.utils import parsedate_to_datetime
                import datetime as dt
                server_dt = parsedate_to_datetime(date_header)
                if server_dt.tzinfo is None:
                    server_dt = server_dt.replace(tzinfo=dt.timezone.utc)
                return server_dt.astimezone()
        except Exception as e:
            print(f"[-] 获取服务器时间失败: {e}")
        
        return None


async def test_concurrency():
    """并发性能测试"""
    client = AsyncHealthClient(max_concurrency=5)
    await client.load_cookies()
    
    if not client.access_hash:
        print("[-] 请先登录获取 Cookie")
        return
    
    # 测试并发查询 7 天
    from datetime import timedelta
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    
    print(f"[*] 测试并发查询 {len(dates)} 天排班...")
    start = time.time()
    
    # 这里需要真实的 unit_id 和 dep_id
    # results = await client.get_schedule_batch("xxx", "xxx", dates)
    
    elapsed = time.time() - start
    print(f"[+] 完成，耗时: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(test_concurrency())
