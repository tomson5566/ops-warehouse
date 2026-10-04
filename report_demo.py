"""report_demo.py — 直接从 ADS 层出报表
不需要再写 SQL 拼接，全部从预聚合的 ADS 表 SELECT 即可。
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
con = duckdb.connect(DB, read_only=True)


def show(title, sql, n_rows=15):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    df = con.execute(sql).df()
    print(df.head(n_rows).to_string(index=False))
    if len(df) > n_rows:
        print(f"\n  ... 共 {len(df):,} 行（仅展示前 {n_rows} 行）")


# ---- 报表 1：月度告警总览 ----
show("【月度告警总览】每个机房每月告警量、P0/P1 严重告警数、平均恢复时长",
     """
     SELECT * FROM ads_alert_monthly_summary
     ORDER BY stat_month DESC, total_alerts DESC
     LIMIT 10
     """)

# ---- 报表 2：1 月 Top10 高 CPU 主机 ----
show("【1 月 Top10 高 CPU 主机】月度 CPU 占用最高 10 台机器",
     """
     SELECT host_id, avg_cpu_pct, peak_cpu_pct
     FROM ads_top_cpu_host_monthly
     WHERE stat_month = '2026-01-01'
     ORDER BY avg_cpu_pct DESC
     LIMIT 10
     """)

# ---- 报表 3：单主机 90 天可用率趋势 ----
show("【H00001 主机 90 天可用率趋势】",
     """
     SELECT stat_date, availability_pct
     FROM ads_host_availability
     WHERE host_id = 'H00001'
     ORDER BY stat_date
     """)

# ---- 报表 4：接口可用率（5xx 占比） ----
show("【接口可用率】按 URL 维度统计 5xx 错误占比",
     """
     SELECT url, req_cnt, err5xx_cnt, availability_pct
     FROM ads_api_availability
     ORDER BY req_cnt DESC
     LIMIT 10
     """)

con.close()
print("\n[OK] 报表输出完毕")