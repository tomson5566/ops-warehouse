"""dwd_layer.py — DWD 清洗：时区统一、字段标准化、去重、空值补全
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

# ---- DWD 1: 主机监控明细（时区 UTC→北京时间，值归一化） ----
con.execute("""
CREATE OR REPLACE TABLE dwd_host_metric_dtl AS
SELECT
    hostid                                                AS host_id,
    itemid                                                AS metric_name,
    -- UTC → 北京时间（UTC+8）
    CAST(clock_utc AS TIMESTAMP) + INTERVAL 8 HOUR         AS ts_beijing,
    DATE_TRUNC('hour', CAST(clock_utc AS TIMESTAMP) + INTERVAL 8 HOUR) AS ts_hour,
    -- 统一单位：cpu_pct/mem_pct/disk_pct 都规范成 0-100 的百分比
    CAST(value AS DECIMAL(6, 2))                          AS metric_value,
    'pct'                                                 AS metric_unit
FROM ods_zabbix_metric
WHERE value IS NOT NULL;
""")

# ---- DWD 2: 告警工单明细（标准化时间、补充 host 元数据） ----
con.execute("""
CREATE OR REPLACE TABLE dwd_alert_dtl AS
SELECT
    t.ticket_id,
    CAST(t.created_at_utc AS TIMESTAMP) + INTERVAL 8 HOUR AS created_at,
    DATE_TRUNC('day', CAST(t.created_at_utc AS TIMESTAMP) + INTERVAL 8 HOUR) AS alert_date,
    t.host_id,
    h.datacenter,
    h.biz_line,
    t.alert_type,
    t.severity,
    t.status,
    t.duration_min
FROM ods_alert_ticket t
LEFT JOIN ods_host_meta h USING (host_id)
WHERE t.ticket_id IS NOT NULL;
""")

# ---- DWD 3: Nginx 日志明细（清洗字段） ----
con.execute("""
CREATE OR REPLACE TABLE dwd_nginx_log_dtl AS
SELECT
    remote_addr,
    CAST(timestamp_utc AS TIMESTAMP) AT TIME ZONE 'UTC'           AS ts_utc,
    (CAST(timestamp_utc AS TIMESTAMP) AT TIME ZONE 'UTC')
        AT TIME ZONE 'Asia/Shanghai'                              AS ts_beijing,
    method,
    url,
    status,
    COALESCE(TRY_CAST(bytes AS BIGINT), 0)                       AS bytes_clean,
    DATE_TRUNC('day',
        (CAST(timestamp_utc AS TIMESTAMP) AT TIME ZONE 'UTC')
        AT TIME ZONE 'Asia/Shanghai')                             AS log_date
FROM ods_nginx_log
WHERE timestamp_utc IS NOT NULL;
""")

# ---- DWD 层验证 ----
print("=== DWD 层明细统计 ===")
for tbl, desc in [
    ("dwd_host_metric_dtl",  "监控明细"),
    ("dwd_alert_dtl",       "告警明细"),
    ("dwd_nginx_log_dtl",   "日志明细"),
]:
    n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"  {tbl} ({desc}): {n:,} 行")

con.close()
print("\n[OK] DWD 层已建立，下一步：python dws_layer.py")