"""dws_layer.py — DWS 汇总：按主机×日、按告警×日×维度、按日志×日×URL
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

# ---- DWS 1: 主机 × 日 监控汇总 ----
con.execute("""
CREATE OR REPLACE TABLE dws_host_metric_daily AS
SELECT
    ts_hour::DATE                              AS stat_date,
    host_id,
    metric_name,
    AVG(metric_value)                          AS avg_value,
    MAX(metric_value)                          AS max_value,
    MIN(metric_value)                          AS min_value,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY metric_value) AS p95_value,
    COUNT(*)                                   AS sample_cnt
FROM dwd_host_metric_dtl
GROUP BY ts_hour::DATE, host_id, metric_name;
""")

# ---- DWS 2: 告警 × 日 汇总（按 severity） ----
con.execute("""
CREATE OR REPLACE TABLE dws_alert_daily AS
SELECT
    alert_date,
    datacenter,
    biz_line,
    severity,
    COUNT(*)                                   AS alert_cnt,
    SUM(duration_min)                          AS total_duration_min,
    AVG(duration_min)                          AS avg_duration_min,
    COUNT(DISTINCT host_id)                    AS affected_host_cnt
FROM dwd_alert_dtl
GROUP BY alert_date, datacenter, biz_line, severity;
""")

# ---- DWS 3: Nginx 日 × URL 汇总 ----
con.execute("""
CREATE OR REPLACE TABLE dws_nginx_daily AS
SELECT
    log_date,
    url,
    COUNT(*)                                   AS req_cnt,
    SUM(bytes_clean)                           AS total_bytes,
    SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) AS err5xx_cnt,
    SUM(CASE WHEN status = 404 THEN 1 ELSE 0 END)  AS err404_cnt
FROM dwd_nginx_log_dtl
GROUP BY log_date, url;
""")

# ---- DWS 层验证 ----
print("=== DWS 层汇总统计 ===")
for tbl, desc in [
    ("dws_host_metric_daily", "主机×日×指标"),
    ("dws_alert_daily",       "告警×日×机房×业务线×级别"),
    ("dws_nginx_daily",       "日志×日×URL"),
]:
    n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"  {tbl} ({desc}): {n:,} 行")

con.close()
print("\n[OK] DWS 层已建立，下一步：python ads_layer.py")