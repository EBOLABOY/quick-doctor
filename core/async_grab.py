#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
异步抢号器 - 高并发版本
使用 asyncio + httpx 实现毫秒级响应
"""
import asyncio
import json
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .async_client import AsyncHealthClient


def load_config(path: str = "config.json") -> Optional[Dict]:
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


def calibrate_time_offset(server_time: datetime) -> float:
    """计算本地与服务器的时间偏移（秒）"""
    local_now = datetime.now(server_time.tzinfo)
    offset = (server_time - local_now).total_seconds()
    return offset


async def wait_until_precise(target_time_str: str, client: AsyncHealthClient) -> datetime:
    """
    毫秒级精准等待
    
    Args:
        target_time_str: 目标时间 (HH:MM:SS)
        client: 异步客户端（用于获取服务器时间）
    
    Returns:
        实际触发时间
    """
    if not target_time_str:
        return datetime.now()
    
    try:
        # 解析目标时间
        target_parts = datetime.strptime(target_time_str, "%H:%M:%S")
        now = datetime.now()
        target = now.replace(
            hour=target_parts.hour,
            minute=target_parts.minute,
            second=target_parts.second,
            microsecond=0
        )
        
        # 如果目标时间已过，立即返回
        if target <= now:
            print(f"[*] 目标时间 {target_time_str} 已过，立即开始")
            return now
        
        # NTP 对时
        print("[*] 正在与服务器对时...")
        time_offset = 0.0
        server_time = await client.get_server_time()
        if server_time:
            time_offset = calibrate_time_offset(server_time)
            print(f"[+] 时间偏移: {time_offset:+.3f} 秒 (本地{'快' if time_offset < 0 else '慢'})")
        else:
            print("[-] 获取服务器时间失败，使用本地时间")
        
        wait_seconds = (target - now).total_seconds()
        print(f"[*] 等待到 {target_time_str} 开始抢号 (还需 {wait_seconds:.1f} 秒)")
        
        # 阶段1: 粗等待 (剩余 > 2秒时用 asyncio.sleep)
        while True:
            remaining = (target - datetime.now()).total_seconds() + time_offset
            if remaining <= 2.0:
                break
            
            # 每秒显示倒计时
            print(f"\r[*] 倒计时: {remaining:.1f} 秒", end="", flush=True)
            await asyncio.sleep(min(1.0, remaining - 2.0))
        
        print(f"\n[*] 进入精准等待模式...")
        
        # 阶段2: 精等待 (剩余 < 2秒时用自旋锁)
        # 注意：这会占用 CPU，但能达到毫秒级精度
        spin_start = datetime.now()
        adjusted_target = target - timedelta(seconds=time_offset)
        
        while datetime.now() < adjusted_target:
            pass  # Busy-wait (自旋锁)
        
        actual_time = datetime.now()
        spin_duration = (actual_time - spin_start).total_seconds() * 1000
        delay = (actual_time - adjusted_target).total_seconds() * 1000
        
        print(f"[+] 时间到! 自旋耗时: {spin_duration:.1f}ms, 触发延迟: {delay:+.1f}ms")
        return actual_time
        
    except ValueError as e:
        print(f"[-] 时间格式错误: {target_time_str}，应为 HH:MM:SS")
        return datetime.now()


async def async_grab_once(config: Dict, client: AsyncHealthClient) -> bool:
    """执行一次异步抢号尝试（并发查询所有日期）"""
    unit_id = config['unit_id']
    dep_id = config['dep_id']
    doctor_ids = set(str(d) for d in config.get('doctor_ids', []))
    member_id = config['member_id']
    target_dates = config.get('target_dates', [])
    time_types = config.get('time_types', ['am', 'pm'])
    preferred_hours = config.get('preferred_hours', [])
    
    # 并发查询所有日期
    print(f"[*] 并发查询 {len(target_dates)} 个日期...")
    start = time.time()
    all_docs = await client.get_schedule_batch(unit_id, dep_id, target_dates)
    elapsed = (time.time() - start) * 1000
    print(f"[+] 查询完成，耗时 {elapsed:.0f}ms，发现 {len(all_docs)} 位医生")
    
    if not all_docs:
        return False
    
    # 筛选目标医生和有号的
    for doc in all_docs:
        doc_id = str(doc.get('doctor_id'))
        
        # 过滤指定医生
        if doctor_ids and doc_id not in doctor_ids:
            continue
        
        schedules = doc.get('schedules', [])
        for sch in schedules:
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
            query_date = sch.get('query_date', doc.get('query_date', ''))
            
            if not schedule_id:
                continue
            
            print(f"[+] 发现号源: {query_date} {doc.get('doctor_name')} - {sch.get('time_type_desc')} (余{left_num})")
            
            # 获取号源详情
            ticket_detail = await client.get_ticket_detail(unit_id, dep_id, schedule_id, member_id=member_id)
            if not ticket_detail:
                continue
            
            times = ticket_detail.get('times') or ticket_detail.get('time_slots') or []
            if not times:
                continue
            
            sch_data = ticket_detail.get('sch_data', '')
            detlid_realtime = ticket_detail.get('detlid_realtime', '')
            level_code = ticket_detail.get('level_code', '')
            
            if not sch_data or not detlid_realtime or not level_code:
                print("[-] 号源详情缺少关键参数，跳过")
                continue
            
            # 选择时段（优先 preferred_hours）
            selected_time = None
            if preferred_hours:
                for t in times:
                    if t.get('name') in preferred_hours:
                        selected_time = t
                        break
            if not selected_time:
                selected_time = times[0]
            
            print(f"[+] 选择时段: {selected_time['name']}")
            
            address_id = (ticket_detail.get("addressId") or "").strip()
            address_text = (ticket_detail.get("address") or "").strip()
            if not address_id or address_id in ("0", "-1") or not address_text:
                print("[-] 缺少城市地址信息：请先在网页端添加/选择城市地址（或在配置里提供 addressId/address）")
                continue

            # 提交订单
            result = await client.submit_order({
                'unit_id': unit_id,
                'dep_id': dep_id,
                'schedule_id': schedule_id,
                'time_type': sch.get('time_type', ''),
                'doctor_id': doc.get('doctor_id', ''),
                'his_doc_id': doc.get('his_doc_id', ''),
                'his_dep_id': doc.get('his_dep_id', ''),
                'detlid': selected_time['value'],
                'member_id': member_id,
                'addressId': address_id,
                'address': address_text,
                'hisMemId': ticket_detail.get("hisMemId", ""),
                'order_no': ticket_detail.get("order_no", ""),
                'disease_input': ticket_detail.get("disease_input", ""),
                'disease_content': ticket_detail.get("disease_content", ""),
                'is_hot': ticket_detail.get("is_hot", ""),
                'sch_date': ticket_detail.get("sch_date", ""),
                'sch_data': sch_data,
                'detlid_realtime': detlid_realtime,
                'level_code': level_code,
            })
            
            if result.get('success') or result.get('status'):
                print(f"\n{'='*50}")
                print(f"[SUCCESS] 抢号成功!")
                print(f"医院: {config.get('unit_name', unit_id)}")
                print(f"科室: {config.get('dep_name', dep_id)}")
                print(f"医生: {doc.get('doctor_name')}")
                print(f"日期: {query_date}")
                print(f"时段: {selected_time['name']}")
                print(f"就诊人: {config.get('member_name', member_id)}")
                if result.get('url'):
                    print(f"详情: {result['url']}")
                print(f"{'='*50}")
                return True
            else:
                print(f"[-] 提交失败: {result.get('msg')}")
    
    return False


async def async_grab_loop(config: Dict):
    """异步抢号主循环"""
    print("=== 91160 异步高并发抢号 ===\n")
    
    # 初始化客户端
    max_concurrency = config.get('max_concurrency', 10)
    client = AsyncHealthClient(max_concurrency=max_concurrency)
    try:
        if not await client.load_cookies():
            print("[-] Cookie 加载失败，请先登录")
            return
        
        if not client.access_hash:
            print("[-] 没有 access_hash，请重新登录")
            return
        
        print(f"[*] 配置加载成功:")
        print(f"    医院: {config.get('unit_name', config['unit_id'])}")
        print(f"    科室: {config.get('dep_name', config['dep_id'])}")
        print(f"    日期: {', '.join(config['target_dates'])}")
        print(f"    就诊人: {config.get('member_name', config['member_id'])}")
        print(f"    并发数: {max_concurrency}")
        
        # 精准等待
        start_time = config.get('start_time')
        if start_time:
            await wait_until_precise(start_time, client)
        
        # 抢号循环
        retry_interval = config.get('retry_interval', 0.3)
        max_retries = config.get('max_retries', 0)
        
        attempt = 0
        while True:
            attempt += 1
            print(f"\n[*] 第 {attempt} 次尝试...")
            
            if await async_grab_once(config, client):
                print("\n[*] 抢号任务完成!")
                break
            
            if max_retries > 0 and attempt >= max_retries:
                print(f"\n[-] 已达最大重试次数 ({max_retries})，退出")
                break
            
            # 使用异步 sleep
            await asyncio.sleep(retry_interval)
    finally:
        await client.close()


async def main():
    """主入口"""
    config = load_config()
    if not config:
        return
    
    # 验证必要配置
    required_fields = ['unit_id', 'dep_id', 'member_id', 'target_dates']
    for field in required_fields:
        if not config.get(field):
            print(f"[-] 配置缺失: {field}")
            return
    
    await async_grab_loop(config)


async def snipe_mode(config: Dict):
    """
    候补捡漏模式 - 低频长挂监控退号
    
    适用场景:
    - 放号后 15-45 分钟 (支付超时退号)
    - 晚间监控 (用户主动退号)
    
    策略:
    - 低频轮询 (30秒/次)，避免封号
    - 发现余号立即切换高频模式
    - 长时间挂机运行
    """
    print("=== 91160 候补捡漏模式 ===\n")
    print("[*] 策略: 低频监控，发现退号立即高频抢夺")
    
    # 捡漏配置
    snipe_interval = config.get('snipe_interval', 30)  # 30秒一次
    rush_interval = config.get('rush_interval', 0.3)   # 发现后 0.3秒一次
    rush_duration = config.get('rush_duration', 60)    # 高频持续 60秒
    
    # 初始化客户端
    max_concurrency = config.get('max_concurrency', 5)
    client = AsyncHealthClient(max_concurrency=max_concurrency)
    try:
        if not await client.load_cookies():
            print("[-] Cookie 加载失败，请先登录")
            return
        
        unit_id = config['unit_id']
        dep_id = config['dep_id']
        target_dates = config.get('target_dates', [])
        
        print(f"[*] 监控配置:")
        print(f"    医院: {config.get('unit_name', unit_id)}")
        print(f"    科室: {config.get('dep_name', dep_id)}")
        print(f"    日期: {', '.join(target_dates)}")
        print(f"    监控间隔: {snipe_interval}秒")
        print()
        
        check_count = 0
        
        while True:
            check_count += 1
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] 第 {check_count} 次监控...")
            
            try:
                # 低频查询
                all_docs = await client.get_schedule_batch(unit_id, dep_id, target_dates)
                
                # 检查是否有余号
                found_slots = []
                for doc in all_docs:
                    left_num = doc.get('total_left_num', 0)
                    if isinstance(left_num, str):
                        left_num = int(left_num) if left_num.isdigit() else 0
                    
                    if left_num > 0:
                        found_slots.append({
                            'doctor_name': doc.get('doctor_name'),
                            'left_num': left_num,
                            'doc': doc
                        })
                
                if found_slots:
                    print(f"\n[!!!] 发现退号! 共 {len(found_slots)} 位医生有号")
                    for slot in found_slots:
                        print(f"    - {slot['doctor_name']} (余 {slot['left_num']})")
                    
                    # 切换高频模式
                    print(f"\n[*] 切换高频抢夺模式 (持续 {rush_duration}秒)...")
                    rush_start = time.time()
                    
                    while time.time() - rush_start < rush_duration:
                        if await async_grab_once(config, client):
                            print("\n[*] 捡漏成功! 任务完成!")
                            
                            # 通知
                            try:
                                from .notifier import notify_success
                                notify_success(
                                    member_name=config.get('member_name', ''),
                                    unit_name=config.get('unit_name', ''),
                                    dep_name=config.get('dep_name', ''),
                                    doctor_name=found_slots[0]['doctor_name'],
                                    date=target_dates[0] if target_dates else '',
                                    time_slot=''
                                )
                            except:
                                pass
                            
                            return
                        
                        await asyncio.sleep(rush_interval)
                    
                    print("[*] 高频抢夺结束，恢复监控模式...")
                else:
                    print(f"    无余号，{snipe_interval}秒后重试...")
                
            except Exception as e:
                print(f"[-] 监控异常: {e}")
            
            await asyncio.sleep(snipe_interval)
    finally:
        await client.close()


async def main_snipe():
    """捡漏模式入口"""
    config = load_config()
    if not config:
        return
    
    required_fields = ['unit_id', 'dep_id', 'member_id', 'target_dates']
    for field in required_fields:
        if not config.get(field):
            print(f"[-] 配置缺失: {field}")
            return
    
    await snipe_mode(config)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--snipe":
        # 捡漏模式: python -m core.async_grab --snipe
        asyncio.run(main_snipe())
    else:
        # 正常模式
        asyncio.run(main())
