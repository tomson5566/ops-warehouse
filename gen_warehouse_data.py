"""gen_warehouse_data.py — 生成模拟运维数据
- 50 台主机 × 90 天 × 每小时 1 条 = 10.8 万条 Zabbix 监控明细
- 5000 条 Nginx 访问日志（带异常）
- 200 条告警工单
"""
import csv
import os
import random
from datetime import date

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

random.seed(42)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

# ---- 主机清单 ----
datacenters = ["机房A", "机房B", "机房C"]
biz_lines   = ["交易", "支付", "登录", "内容", "后台"]
hosts = []
with open(os.path.join(DATA, "host_meta.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["host_id", "host_name", "datacenter", "biz_line", "ip"])
    for i in range(1, 51):
        h = f"H{i:05d}"
        hosts.append(h)
        w.writerow([
            h,
            f"host_{i:03d}",
            random.choice(datacenters),
            random.choice(biz_lines),
            f"10.0.{(i // 254) + 1}.{(i % 254) + 1}",
        ])

# ---- Zabbix 监控明细（ODS 原样） ----
start = date(2026, 1, 1)
metrics = ["cpu_pct", "mem_pct", "disk_pct", "net_in_kbps"]
zb_rows = 0
with open(os.path.join(DATA, "zabbix_export.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["hostid", "itemid", "clock_utc", "value"])
    for day in range(90):
        for hour in range(24):
            for h in hosts:
                for m in metrics:
                    base = 30 if "cpu" in m else 50 if "mem" in m else 60 if "disk" in m else 100
                    val  = base + random.gauss(0, 10)
                    val  = max(0, min(100, val))
                    if random.random() < 0.005:
                        val = 100
                    clock = f"2026-{(day // 28) + 1:02d}-{(day % 28) + 1:02d} {hour:02d}:00:00"
                    w.writerow([h, m, clock, f"{val:.2f}"])
                    zb_rows += 1

# ---- Nginx 访问日志（带异常） ----
status_codes = [200, 200, 200, 200, 200, 200, 304, 404, 500, 502, 503]
with open(os.path.join(DATA, "nginx_access.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["remote_addr", "timestamp_utc", "method", "url", "bytes", "status"])
    for i in range(5000):
        w.writerow([
            f"192.168.{random.randint(0, 255)}.{random.randint(0, 255)}",
            f"2026-01-{random.randint(1, 28):02d}T{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00Z",
            random.choice(["GET", "POST", "PUT"]),
            random.choice(["/api/order", "/api/login", "/api/pay", "/static/img"]),
            random.randint(100, 50000),
            random.choice(status_codes),
        ])

# ---- 告警工单 ----
alert_types = ["CPU飙高", "磁盘满", "服务挂", "慢SQL", "网络抖动"]
with open(os.path.join(DATA, "alert_tickets.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["ticket_id", "created_at_utc", "host_id", "alert_type",
                "severity", "status", "duration_min"])
    for i in range(1, 201):
        h = random.choice(hosts)
        sev = random.choice(["P0", "P1", "P2", "P3"])
        st  = random.choice(["已恢复", "处理中", "待处理"])
        dur = random.randint(5, 240)
        w.writerow([
            f"T{i:05d}",
            f"2026-01-{random.randint(1, 28):02d} {random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00",
            h, random.choice(alert_types), sev, st, dur,
        ])

print("生成完成：", DATA)
for fn in sorted(os.listdir(DATA)):
    n = sum(1 for _ in open(os.path.join(DATA, fn), encoding="utf-8")) - 1
    print(f"  {fn}: {n:,} 行")
print(f"\n共生成 {zb_rows:,} 条 Zabbix 监控明细 + 5,000 条日志 + 200 条工单。")