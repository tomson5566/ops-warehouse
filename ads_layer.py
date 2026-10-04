"""ads_layer.py — ADS 应用层：直接喂给周报/月报
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

# ---- ADS 1: 每日主机可用率（CPU < 80% 的样本占比） ----
con.execute("""
CREATE OR REPLACE TABLE ads_host_availability AS
SELECT
    stat_date,
    host_id,
    ROUND(
        SUM(CASE WHEN avg_value < 80 THEN 1 ELSE 0 END)::DECIMAL
        / COUNT(*) * 100, 2
    )                                          AS availability_pct
FROM dws_host_metric_daily
WHERE metric_name = 'cpu_pct'
GROUP BY stat_date, host_id;
""")

# ---- ADS 2: 月度 Top10 高 CPU 主机 ----
con.execute("""
CREATE OR REPLACE TABLE ads_top_cpu_host_monthly AS
SELECT
    DATE_TRUNC('month', stat_date)             AS stat_month,
    host_id,
    ROUND(AVG(avg_value), 2)                   AS avg_cpu_pct,
    ROUND(MAX(max_value), 2)                   AS peak_cpu_pct
FROM dws_host_metric_daily
WHERE metric_name = 'cpu_pct'
GROUP BY DATE_TRUNC('month', stat_date), host_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY DATE_TRUNC('month', stat_date)
    ORDER BY AVG(avg_value) DESC
) <= 10;
""")

# ---- ADS 3: 告警月度总览 ----
con.execute("""
CREATE OR REPLACE TABLE ads_alert_monthly_summary AS
SELECT
    DATE_TRUNC('month', alert_date)            AS stat_month,
    datacenter,
    SUM(alert_cnt)                             AS total_alerts,
    SUM(CASE WHEN severity = 'P0' THEN alert_cnt ELSE 0 END) AS p0_alerts,
    SUM(CASE WHEN severity = 'P1' THEN alert_cnt ELSE 0 END) AS p1_alerts,
    ROUND(AVG(avg_duration_min), 1)            AS avg_recovery_min
FROM dws_alert_daily
GROUP BY DATE_TRUNC('month', alert_date), datacenter;
""")

# ---- ADS 4: 接口可用率（5xx 占比） ----
con.execute("""
CREATE OR REPLACE TABLE ads_api_availability AS
SELECT
    log_date,
    url,
    req_cnt,
    err5xx_cnt,
    ROUND((req_cnt - err5xx_cnt)::DECIMAL / NULLIF(req_cnt, 0) * 100, 2)
        AS availability_pct
FROM dws_nginx_daily
WHERE url LIKE '/api/%';
""")

print("=== ADS 层应用表 ===")
for tbl in [
    "ads_host_availability",
    "ads_top_cpu_host_monthly",
    "ads_alert_monthly_summary",
    "ads_api_availability",
]:
    n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"  {tbl}: {n:,} 行")

con.close()
print("\n[OK] ADS 层已建立，下一步：python report_demo.py")