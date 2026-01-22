#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动抢号脚本 - 读取配置文件，循环抢号直到成功
"""
import json
import time
import datetime
import sys
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

def wait_until(target_time_str, client=None, use_server_time=False):
    """等待到指定时间"""
    if not target_time_str:
        return
    
    try:
        now = datetime.datetime.now()
        if use_server_time and client:
            server_now = client.get_server_datetime()
            if server_now:
                now = server_now.replace(tzinfo=None)
                print(f"[*] 当前服务器时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print("[-] 获取服务器时间失败，使用本地时间")
        target = datetime.datetime.strptime(target_time_str, "%H:%M:%S")
        target = now.replace(hour=target.hour, minute=target.minute, second=target.second, microsecond=0)
        
        # 如果目标时间已过，跳过等待
        if target <= now:
            print(f"[*] 目标时间 {target_time_str} 已过，立即开始")
            return
        
        wait_seconds = (target - now).total_seconds()
        print(f"[*] 等待到 {target_time_str} 开始抢号 (还需 {wait_seconds:.0f} 秒)")
        
        # 每秒更新倒计时
        while datetime.datetime.now() < target:
            remaining = (target - datetime.datetime.now()).total_seconds()
            if remaining > 0:
                print(f"\r[*] 倒计时: {remaining:.1f} 秒", end="", flush=True)
                time.sleep(min(1, remaining))
        print("\n[*] 时间到，开始抢号!")
    except ValueError:
        print(f"[-] 时间格式错误: {target_time_str}，应为 HH:MM:SS")

def grab(config, client):
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
        print(f"\n[*] 查询 {target_date} 排班...")
        docs = client.get_schedule(unit_id, dep_id, target_date)
        
        if not docs:
            print(f"[-] {target_date} 无排班数据")
            continue
        
        # 筛选目标医生
        for doc in docs:
            doc_id = str(doc.get('doctor_id'))
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
                if not schedule_id:
                    continue
                
                print(f"[+] 发现可用号源: {doc.get('doctor_name')} - {sch.get('time_type_desc')} (余{left_num})")
                
                # 获取号源详情
                ticket_detail = client.get_ticket_detail(unit_id, dep_id, schedule_id)
                if not ticket_detail:
                    # print(f"[-] 获取号源详情失败")
                    continue
                if not ticket_detail.get('times') and not ticket_detail.get('time_slots'):
                    continue
                sch_data = ticket_detail.get('sch_data', '')
                detlid_realtime = ticket_detail.get('detlid_realtime', '')
                level_code = ticket_detail.get('level_code', '')
                if not sch_data or not detlid_realtime or not level_code:
                    print("[-] 号源详情缺少关键参数，跳过该号源")
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
                
                print(f"[+] 选择时段: {selected_time['name']}")
                
                # 提交订单
                sch_date = sch.get('to_date', target_date)
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
                    sch_data=sch_data,
                    level_code=level_code,
                    sch_date=sch_date,
                    to_date=sch_date,
                    detlid_realtime=detlid_realtime,
                    detl_name=selected_time['name']
                )
                
                if result and (result.get('success') or result.get('status')):
                    print(f"\n{'='*50}")
                    print(f"[SUCCESS] 抢号成功!")
                    print(f"医院: {config['unit_name']}")
                    print(f"科室: {config['dep_name']}")
                    print(f"医生: {doc.get('doctor_name')}")
                    print(f"日期: {target_date}")
                    print(f"时段: {selected_time['name']}")
                    print(f"就诊人: {config['member_name']}")
                    if result.get('url'):
                        print(f"详情: {result['url']}")
                    print(f"{'='*50}")
                    return True
                else:
                    msg = result.get('msg') if isinstance(result, dict) else result
                    print(f"[-] 提交失败: {msg}")
    
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
