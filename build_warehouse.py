"""build_warehouse.py — 一键搭起 4 层运维数仓
=============================================
依次执行：
    1) 生成模拟数据
    2) ODS 落盘
    3) DWD 清洗
    4) DWS 汇总
    5) ADS 应用
    6) 输出报表

运行：python build_warehouse.py
产出：operational_warehouse.duckdb（约 20-50 MB）
"""
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    ("Step 1/6：生成模拟运维数据", "gen_warehouse_data.py"),
    ("Step 2/6：建 ODS 层（原始落盘）", "ods_layer.py"),
    ("Step 3/6：建 DWD 层（清洗）",   "dwd_layer.py"),
    ("Step 4/6：建 DWS 层（汇总）",   "dws_layer.py"),
    ("Step 5/6：建 ADS 层（应用）",   "ads_layer.py"),
    ("Step 6/6：输出 ADS 报表",       "report_demo.py"),
]


def banner(title):
    print()
    print("#" * 70)
    print(f"# {title}")
    print("#" * 70)


def run_step(script):
    path = os.path.join(HERE, script)
    print(f"\n>>> 运行 {script}\n")
    subprocess.run([sys.executable, path], check=True)


def main():
    for title, script in STEPS:
        banner(title)
        run_step(script)

    banner("全部完成")
    db = os.path.join(HERE, "operational_warehouse.duckdb")
    if os.path.exists(db):
        mb = os.path.getsize(db) / (1024 * 1024)
        print(f"数据库已生成：{db}（{mb:.1f} MB）")
    print("下一步：")
    print("  - 双击 operational_warehouse.duckdb 用 DuckDB CLI 打开")
    print("  - 或 python report_demo.py 再看一次报表")
    print("  - 或接入 Grafana / DataEase：把该文件作为数据源即可")


if __name__ == "__main__":
    main()