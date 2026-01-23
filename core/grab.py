#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动抢号脚本 - 读取配置文件，循环抢号直到成功
"""
import json
import time
import datetime
import sys
from typing import Callable, Optional
from .client import HealthClient

def load_config(path="config.json"):
    """加载配置文件"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[-] 配置文件 {path} 不存在，请先运行 python setup.py")
        return None
    except json.JSONDecodeError as e:
        print(f"[-] 配置文件格式错误: {e}")
        return None

def calibrate_time_offset(client):
    """
    NTP 对时：计算本地与服务器的时间偏移
    
    Returns:
        float: 时间偏移（秒），正数表示本地慢，负数表示本地快
    """
    if not client:
        return 0.0
    
    local_before = datetime.datetime.now()
    server_time = client.get_server_datetime()
    local_after = datetime.datetime.now()
    
    if server_time:
        # 计算 RTT 并估算真实服务器时间
        rtt = (local_after - local_before).total_seconds()
        local_mid = local_before + datetime.timedelta(seconds=rtt/2)
        
        # 转换为无时区进行比较
        server_naive = server_time.replace(tzinfo=None)
        offset = (server_naive - local_mid).total_seconds()
        
        return offset
    
    return 0.0


def wait_until(target_time_str, client=None, use_server_time=False):
    """
    毫秒级精准等待
    
    优化策略:
    1. NTP 对时：计算本地与服务器的时间偏移
    2. 粗等待：剩余 > 2秒时用 time.sleep()
    3. 精等待：剩余 < 2秒时用自旋锁 (CPU 空转)
    """
    if not target_time_str:
        return
    
    try:
        now = datetime.datetime.now()
        
        # NTP 对时
        time_offset = 0.0
        if use_server_time and client:
            print("[*] 正在与服务器对时...")
            time_offset = calibrate_time_offset(client)
            if time_offset != 0:
                print(f"[+] 时间偏移: {time_offset:+.3f} 秒 (本地{'快' if time_offset < 0 else '慢'})")
            else:
                print("[-] 获取服务器时间失败，使用本地时间")
        
        # 解析目标时间
        target = datetime.datetime.strptime(target_time_str, "%H:%M:%S")
        target = now.replace(hour=target.hour, minute=target.minute, second=target.second, microsecond=0)
        
        # 应用时间偏移：如果本地慢，需要提前触发
        adjusted_target = target - datetime.timedelta(seconds=time_offset)
        
        # 如果目标时间已过，跳过等待
        if adjusted_target <= now:
            print(f"[*] 目标时间 {target_time_str} 已过，立即开始")
            return
        
        wait_seconds = (adjusted_target - now).total_seconds()
        print(f"[*] 等待到 {target_time_str} 开始抢号 (还需 {wait_seconds:.1f} 秒)")
        
        # 阶段1: 粗等待 (剩余 > 2秒时用 sleep)
        while True:
            remaining = (adjusted_target - datetime.datetime.now()).total_seconds()
            if remaining <= 2.0:
                break
            print(f"\r[*] 倒计时: {remaining:.1f} 秒", end="", flush=True)
            time.sleep(min(1.0, remaining - 2.0))
        
        print(f"\n[*] 进入精准等待模式 (自旋锁)...")
        
        # 阶段2: 精等待 (剩余 < 2秒时用自旋锁)
        spin_start = datetime.datetime.now()
        while datetime.datetime.now() < adjusted_target:
            pass  # Busy-wait (自旋锁) - 占用 CPU 但精度高
        
        actual_time = datetime.datetime.now()
        spin_duration = (actual_time - spin_start).total_seconds() * 1000
        delay = (actual_time - adjusted_target).total_seconds() * 1000
        
        print(f"[+] 时间到! 自旋耗时: {spin_duration:.1f}ms, 触发延迟: {delay:+.1f}ms")
        
    except ValueError:
        print(f"[-] 时间格式错误: {target_time_str}，应为 HH:MM:SS")

def _emit_log(on_log: Optional[Callable], message: str, level: str = "info"):
    if on_log:
        on_log(message, level)
    else:
        print(message)


def grab(config, client, on_log: Optional[Callable] = None, stop_event: Optional[object] = None,
         on_success: Optional[Callable] = None):
    """执行一次抢号尝试"""
    unit_id = config['unit_id']
    dep_id = config['dep_id']
    doctor_ids = set(str(d) for d in config.get('doctor_ids', []))
    member_id = config['member_id']
    target_dates = config.get('target_dates', [])
    time_types = config.get('time_types', ['am', 'pm'])
    preferred_hours = config.get('preferred_hours', [])
    
    # 获取排班
    for target_date in target_dates:
        if stop_event and stop_event.is_set():
            return False
        _emit_log(on_log, f"\n[*] 查询 {target_date} 排班...", "info")
        docs = client.get_schedule(unit_id, dep_id, target_date)
        
        if not docs:
            _emit_log(on_log, f"[-] {target_date} 无排班数据", "warn")
            continue
        
        # 筛选目标医生
        for doc in docs:
            if stop_event and stop_event.is_set():
                return False
            doc_id = str(doc.get('doctor_id'))
            if doctor_ids and doc_id not in doctor_ids:
                continue
            
            schedules = doc.get('schedules', [])
            for sch in schedules:
                if stop_event and stop_event.is_set():
                    return False
                # 检查时段类型
                time_type = sch.get('time_type', '')
                if time_type not in time_types:
                    continue
                
                # 检查余号
                try:
                    left_num = int(str(sch.get('left_num', 0)).strip() or 0)
                except ValueError:
                    left_num = 0
                if left_num <= 0:
                    continue
                
                schedule_id = sch.get('schedule_id')
                if not schedule_id:
                    continue
                
                _emit_log(
                    on_log,
                    f"[+] 发现可用号源: {doc.get('doctor_name')} - {sch.get('time_type_desc')} (余{left_num})",
                    "success",
                )
                
                # 获取号源详情
                ticket_detail = client.get_ticket_detail(unit_id, dep_id, schedule_id, member_id=member_id)
                if not ticket_detail:
                    # print(f"[-] 获取号源详情失败")
                    continue
                if not ticket_detail.get('times') and not ticket_detail.get('time_slots'):
                    continue
                sch_data = ticket_detail.get('sch_data', '')
                detlid_realtime = ticket_detail.get('detlid_realtime', '')
                level_code = ticket_detail.get('level_code', '')
                if not sch_data or not detlid_realtime or not level_code:
                    _emit_log(on_log, "[-] 号源详情缺少关键参数，跳过该号源", "warn")
                    continue
                
                # 选择时段
                times = ticket_detail.get('times') or ticket_detail.get('time_slots') or []
                selected_time = None
                
                if preferred_hours:
                    for t in times:
                        if t['name'] in preferred_hours:
                            selected_time = t
                            break
                
                if not selected_time:
                    selected_time = times[0]  # 默认选第一个
                
                _emit_log(on_log, f"[+] 选择时段: {selected_time['name']}", "info")

                if stop_event and stop_event.is_set():
                    return False

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

                address_id = (
                    _normalize_address_id(config.get("addressId"))
                    or _normalize_address_id(config.get("address_id"))
                    or _normalize_address_id(ticket_detail.get("addressId"))
                    or _normalize_address_id(ticket_detail.get("address_id"))
                )
                address_text = (
                    _normalize_address_text(config.get("address"))
                    or _normalize_address_text(ticket_detail.get("address"))
                )
                if not address_id or not address_text:
                    addresses = ticket_detail.get("addresses") or []
                    for item in addresses:
                        cand_id = _normalize_address_id(item.get("id"))
                        cand_text = _normalize_address_text(item.get("text"))
                        if not cand_id or not cand_text:
                            continue
                        address_id = cand_id
                        address_text = cand_text
                        _emit_log(on_log, f"未配置地址，使用页面地址: {address_text}", "warn")
                        break

                if not address_id or not address_text:
                    _emit_log(
                        on_log,
                        "缺少城市地址信息：请先在网页端添加/选择城市地址（或在配置里提供 addressId/address）",
                        "error",
                    )
                    continue
                
                # 提交订单
                result = client.submit_order(
                    unit_id=unit_id,
                    dep_id=dep_id,
                    schedule_id=schedule_id,
                    time_type=sch.get('time_type', ''),
                    doctor_id=doc.get('doctor_id', ''),
                    his_doc_id=doc.get('his_doc_id', ''),
                    his_dep_id=doc.get('his_dep_id', ''),
                    detlid=selected_time['value'],
                    member_id=member_id,
                    addressId=address_id,
                    address=address_text,
                    sch_data=sch_data,
                    level_code=level_code,
                    detlid_realtime=detlid_realtime,
                    sch_date=ticket_detail.get("sch_date", ""),
                    hisMemId=ticket_detail.get("hisMemId", ""),
                    order_no=ticket_detail.get("order_no", ""),
                    disease_input=ticket_detail.get("disease_input", ""),
                    disease_content=ticket_detail.get("disease_content", ""),
                    is_hot=ticket_detail.get("is_hot", ""),
                )
                
                if result and (result.get('success') or result.get('status')):
                    unit_name = config.get('unit_name', config.get('unit_id', ''))
                    dep_name = config.get('dep_name', config.get('dep_id', ''))
                    member_name = config.get('member_name', config.get('member_id', ''))
                    _emit_log(on_log, f"\n{'='*50}", "success")
                    _emit_log(on_log, "[SUCCESS] 抢号成功!", "success")
                    _emit_log(on_log, f"医院: {unit_name}", "success")
                    _emit_log(on_log, f"科室: {dep_name}", "success")
                    _emit_log(on_log, f"医生: {doc.get('doctor_name')}", "success")
                    _emit_log(on_log, f"日期: {target_date}", "success")
                    _emit_log(on_log, f"时段: {selected_time['name']}", "success")
                    _emit_log(on_log, f"就诊人: {member_name}", "success")
                    if result.get('url'):
                        _emit_log(on_log, f"详情: {result['url']}", "success")
                    _emit_log(on_log, f"{'='*50}", "success")
                    if on_success:
                        on_success({
                            'unit_name': unit_name,
                            'dep_name': dep_name,
                            'doctor_name': doc.get('doctor_name', ''),
                            'date': target_date,
                            'time_slot': selected_time.get('name', ''),
                            'member_name': member_name,
                            'url': result.get('url', ''),
                        })
                    return True
                else:
                    msg = result.get('msg') if isinstance(result, dict) else result
                    _emit_log(on_log, f"[-] 提交失败: {msg}", "error")
    
    return False

def main():
    print("=== 91160 自动抢号脚本 ===\n")
    
    # 加载配置
    config = load_config()
    if not config:
        return
    
    # 验证配置
    required_fields = ['unit_id', 'dep_id', 'member_id', 'target_dates']
    for field in required_fields:
        if not config.get(field):
            print(f"[-] 配置缺失: {field}")
            return
    
    print(f"[*] 配置加载成功:")
    print(f"    医院: {config.get('unit_name', config['unit_id'])}")
    print(f"    科室: {config.get('dep_name', config['dep_id'])}")
    print(f"    目标日期: {', '.join(config['target_dates'])}")
    print(f"    就诊人: {config.get('member_name', config['member_id'])}")
    
    # 初始化客户端
    client = HealthClient()
    if not client.login():
        print("[-] 登录失败")
        return
    
    # 等待开始时间
    wait_until(config.get('start_time'), client, config.get('use_server_time', False))
    
    # 抢号循环
    retry_interval = config.get('retry_interval', 0.5)
    max_retries = config.get('max_retries', 0)  # 0 表示无限重试
    
    attempt = 0
    while True:
        attempt += 1
        print(f"\n[*] 第 {attempt} 次尝试...")
        
        if grab(config, client):
            print("\n[*] 抢号任务完成!")
            break
        
        if max_retries > 0 and attempt >= max_retries:
            print(f"\n[-] 已达最大重试次数 ({max_retries})，退出")
            break
        
        print(f"[*] {retry_interval} 秒后重试...")
        time.sleep(retry_interval)

if __name__ == "__main__":
    main()
