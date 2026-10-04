"""ods_layer.py — 把 CSV 原样落进 DuckDB 的 ODS 层
不动数据，只做 COPY。清洗在 DWD 做。
"""
import os
import sys
import duckdb

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "operational_warehouse.duckdb")

con = duckdb.connect(DB)

# 主机元数据
con.execute("""
CREATE TABLE IF NOT EXISTS ods_host_meta AS
SELECT * FROM read_csv_auto('data/host_meta.csv');
""")

# Zabbix 监控明细（ODS：保留原始 UTC 时间、原始字段名）
con.execute("""
CREATE TABLE IF NOT EXISTS ods_zabbix_metric AS
SELECT * FROM read_csv_auto('data/zabbix_export.csv');
""")

# Nginx 日志（ODS：保留原始 UTC 时间戳）
con.execute("""
CREATE TABLE IF NOT EXISTS ods_nginx_log AS
SELECT * FROM read_csv_auto('data/nginx_access.csv');
""")

# 告警工单（ODS：保留原始 UTC 时间）
con.execute("""
CREATE TABLE IF NOT EXISTS ods_alert_ticket AS
SELECT * FROM read_csv_auto('data/alert_tickets.csv');
""")

# ODS 层验证
print("=== ODS 层表清单 ===")
for tbl in con.execute("SHOW TABLES").fetchall():
    name = tbl[0]
    if name.startswith("ods_"):
        n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name}: {n:,} 行")

con.close()
print("\n[OK] ODS 层已建立，下一步：python dwd_layer.py")