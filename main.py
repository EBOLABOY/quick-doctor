from core.client import HealthClient
import sys
import json

def select_from_list(items, display_func_or_keys, return_key=None):
    """通用的列表选择助手函数。支持 func 或 key_list"""
    if not items:
        print("[-] 列表为空")
        return None
    
    for idx, item in enumerate(items):
        name = "未知"
        if callable(display_func_or_keys):
            try: name = display_func_or_keys(item)
            except: pass
        else:
            for k in display_func_or_keys:
                if k in item:
                    name = item[k]
                    break
        print(f"[{idx}] {name}")
    
    while True:
        try:
            choice = input(f"请输入序号 (0-{len(items)-1}): ")
            idx = int(choice)
            if 0 <= idx < len(items):
                return items[idx] if return_key is None else items[idx].get(return_key)
        except ValueError:
            pass
        print("[-] 输入无效，请重新输入")

def main():
    print("=== 91160 自动抢号助手 (CLI交互版) ===")
    
    # 1. 初始化与登录
    # 1. 初始化与登录
    client = HealthClient()
    if not client.login():
        print("[-] 登录失败，程序退出")
        return

    # 2. 选择城市 (目前默认深圳)
    city_id = 5 
    print(f"\n[*] 当前城市: 深圳 (ID: {city_id})")
    
    # 3. 选择医院
    print("\n[*] 正在获取医院列表...")
    hospitals = client.get_hospitals_by_city(city_id)
    if not hospitals:
        print("[-] 未获取到医院信息 (列表为空)")
        return
    
    # 自动识别 Key
    sample = hospitals[0]
    # print(f"[DEBUG] Hospital Sample: {sample}") # 调试用

    hospital_name_keys = ['unit_name', 'name']
    
    # 支持简单的搜索过滤
    filter_key = input("请输入医院关键字进行过滤 (直接回车显示全部): ").strip()
    if filter_key:
        filtered = []
        for h in hospitals:
            name = next((h[k] for k in hospital_name_keys if k in h), "")
            if filter_key in name:
                filtered.append(h)
        hospitals = filtered
    
    selected_hospital = select_from_list(hospitals, hospital_name_keys)
    if not selected_hospital: return
    
    unit_id = selected_hospital.get('unit_id', selected_hospital.get('id'))
    unit_name = selected_hospital.get('unit_name', selected_hospital.get('name'))
    print(f"[+] 已选择: {unit_name} (ID: {unit_id})")

    # 4. 选择科室
    print("\n[*] 正在获取科室列表...")
    dep_categories = client.get_deps_by_unit(unit_id)
    
    all_deps = []
    # 展平科室结构
    if isinstance(dep_categories, list):
        for cat in dep_categories:
            if 'childs' in cat and cat['childs']:
                all_deps.extend(cat['childs'])
            elif 'dep_id' in cat: # 说明已经是扁平的
                all_deps.append(cat)
    
    if not all_deps:
        print(f"[-] 未找到科室信息。原始响应: {json.dumps(dep_categories)[:200]}")
        return

    filter_dep = input("请输入科室关键字进行过滤 (直接回车显示全部): ").strip()
    if filter_dep:
        all_deps = [d for d in all_deps if filter_dep in d.get('dep_name', d.get('name', ''))]

    dep_keys = ['dep_name', 'name']
    selected_dep = select_from_list(all_deps, dep_keys)
    if not selected_dep: return
    
    dep_id = selected_dep.get('dep_id', selected_dep.get('id'))
    dep_name = selected_dep.get('dep_name', selected_dep.get('name'))
    print(f"\n[+] 已选择: {dep_name} (ID: {dep_id})")

    # 5. 选择日期
    import datetime
    today = datetime.date.today()
    dates = [(today + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    
    print("\n[*] 请选择就诊日期:")
    for idx, d in enumerate(dates):
        print(f"[{idx}] {d}")
        
    date_idx = 0
    while True:
        try:
            choice = input(f"请输入序号 (0-6) [默认0]: ").strip()
            if not choice: break
            date_idx = int(choice)
            if 0 <= date_idx < len(dates): break
        except ValueError:
            pass
    selected_date = dates[date_idx]
    print(f"[+] 已选择日期: {selected_date}")

    # 6. 查询排班
    print("\n[*] 正在获取医生排班...")
    docs = client.get_schedule(unit_id, dep_id, selected_date)
    
    if not docs:
        print("[-] 该日期详情暂无排班或获取失败")
        return

    # 7. 选择医生
    print("\n[*] 可预约医生列表:")
    # 过滤掉无有效排班的医生 (client.py 已经做了初步处理，但这里再次确认)
    available_docs = [d for d in docs if d.get('schedules')]

    if not available_docs:
        print("[-] 当前无医生可预约 (所有医生均无号)")
        choice = input("是否显示所有医生(含无号)? (y/n): ")
        if choice.lower() == 'y':
            available_docs = docs
        else:
            return

    def doc_display(x):
        schedules = x.get('schedules', [])
        slots_desc = []
        for s in schedules:
            status = s.get('y_state_desc', '')
            left = s.get('left_num', '0')
            slots_desc.append(f"{s.get('time_type_desc')}:{status}(余{left})")
        
        slots_str = ", ".join(slots_desc) if slots_desc else "无号"
        return f"{x.get('doctor_name')} -- [{slots_str}] -- {x.get('expert', '')[:20]}..."

    selected_doc = select_from_list(available_docs, doc_display)
    if not selected_doc: return
    
    print(f"[+] 已选择医生: {selected_doc.get('doctor_name')}")
    
    # 选择具体时段
    schedules = selected_doc.get('schedules', [])
    selected_sch = None
    
    if not schedules:
         print("[-] 该医生暂无可预约号源")
         return
    elif len(schedules) == 1:
        selected_sch = schedules[0]
        print(f"[+] 自动选择唯一时段: {selected_sch.get('time_type_desc')}")
    else:
        print("\n[*] 请选择预约时段:")
        selected_sch = select_from_list(schedules, lambda x: f"{x.get('time_type_desc')} {x.get('y_state_desc')} (余{x.get('left_num')})")
    
    if not selected_sch: return

    sch_id = selected_sch.get('schedule_id')
    print(f"[+] Schedule ID: {sch_id}")

    # 7. 获取具体的号源时间段
    print("\n[*] 正在获取号源详情...")
    ticket_detail = client.get_ticket_detail(unit_id, dep_id, sch_id)
    time_slots = None
    if ticket_detail:
        time_slots = ticket_detail.get('times') or ticket_detail.get('time_slots')
    if not time_slots:
        print("[-] 获取号源时间段失败或已约满")
        return
        
    print("\n[*] 可选时间段:")
    selected_time = select_from_list(time_slots, lambda x: x['name'])
    print(f"[+] 已选择时间: {selected_time['name']}")

    # 8. 选择就诊人
    print("\n[*] 正在获取就诊人列表...")
    members = client.get_members()
    if not members:
        print("[-] 未找到就诊人，请先在 91160 App 或网页端添加家庭成员")
        return
        
    print("\n[*] 请选择就诊人:")
    selected_member = select_from_list(members, lambda x: f"{x['name']} ({'已认证' if x['certified'] else '未认证'})")
    print(f"[+] 已选择就诊人: {selected_member['name']}")

    # 9. 确认下单
    print("\n" + "="*30)
    print("请确认订单信息:")
    print(f"医院: {unit_name}")
    print(f"科室: {dep_name}")
    print(f"日期: {selected_date}")
    print(f"医生: {selected_doc.get('doctor_name')}")
    print(f"时段: {selected_time['name']}")
    print(f"就诊人: {selected_member['name']}")
    print("="*30)
    
    confirm = input("确认提交去挂号吗? (y/n): ")
    if confirm.lower() != 'y':
        print("[-] 已取消")
        return

    # 10. 提交订单
    sch_date = selected_sch.get('to_date', selected_date)
    sch_data = ticket_detail.get('sch_data', '')
    detlid_realtime = ticket_detail.get('detlid_realtime', '')
    level_code = ticket_detail.get('level_code', '')
    if not sch_data or not detlid_realtime or not level_code:
        print("[-] 号源详情缺少关键参数，请重新登录或刷新号源")
        return

    params = {
        'unit_id': unit_id,
        'dep_id': dep_id,
        'schedule_id': sch_id,
        'his_dep_id': selected_doc.get('his_dep_id', ''),
        'sch_date': sch_date,
        'time_type': selected_sch.get('time_type', selected_doc.get('time_type', '')),
        'doctor_id': selected_doc.get('doctor_id', ''),
        'his_doc_id': selected_doc.get('his_doc_id', ''),
        'detlid': selected_time['value'],
        'detl_name': selected_time['name'],
        'member_id': selected_member['id'],
        # 隐藏参数
        'sch_data': sch_data,
        'detlid_realtime': detlid_realtime,
        'level_code': level_code
    }
    
    print("[*] 正在提交订单...")
    res = client.submit_order(**params)
    if res.get('success') or res.get('status'):
        msg = res.get('msg', 'OK')
        if res.get('url'):
            print(f"\n[SUCCESS] {msg} - {res['url']}")
        else:
            print(f"\n[SUCCESS] {msg}")
    else:
        print(f"\n[FAILED] {res.get('msg', res)}")

if __name__ == "__main__":
    main()
