# DuckDB运维数据仓库实战

## 前言：运维人的数仓自由

![cover_ops_warehouse](C:\Users\18960\.minimax-agent-cn\projects\ops-warehouse\imgs\cover_ops_warehouse.png)

很多运维团队都卡在同一个坑里：Zabbix 导出一堆 CSV，Nginx 日志一天几百兆，告警工单散在三个系统——领导要"近一季度各机房的 P0 告警趋势"，你只能 SQL 拼凑 + Excel 透视，忙半天还容易出错。

**有没有"轻量级"的数仓方案？** 有。DuckDB 单文件就能搞定，零 Hadoop 集群、零 Kafka、零 Flink，半小时搭出 4 层架构（ODS / DWD / DWS / ADS），直接出 ADS 报表喂给周报月报。

今天这篇文章就把这条流水线完整跑一遍给你看。文末有 7 个脚本，复制粘贴即可。

---

## 一、4 层架构回顾

经典的 ODS → DWD → DWS → ADS 4 层架构，在运维场景下的角色分工：

| 层级 | 名称 | 作用 | 运维场景示例 |
|---|---|---|---|
| ODS | 原始数据层 | 不动原样落盘 | Zabbix 导出 CSV、Nginx 原始日志、告警工单 |
| DWD | 明细数据层 | 清洗/标准化/补全 | 时区统一、单位统一、去重、字段补全 |
| DWS | 汇总数据层 | 按维度轻度聚合 | 主机×日、服务×时 |
| ADS | 应用数据层 | 报表即用 | 可用率、TopN 慢查询、月度复盘报表 |

每一层职责单一、可独立重跑：DWD 错了重跑 DWD，DWS 错了重跑 DWS，**新人接手也能 5 分钟看懂全貌**。

---

## 二、为什么选 DuckDB而不是 Hive/Spark

两种主流搭法：

- **Hive/Spark**：需要装 Hadoop 集群、YARN、Hive Metastore，单机笔记本跑不动，团队运维成本高。
- **DuckDB**：单文件、零部署、`pip install duckdb` 一行搞定。

**DuckDB 对运维团队的几大杀手锏**：

- ✅ **零部署**：`pip install duckdb` 一行搞定
- ✅ **单文件**：整个数仓就一个 `.duckdb` 文件，备份靠 `cp`
- ✅ **标准 SQL**：和 MySQL / PostgreSQL 兼容，所有运维 SQL 模板可直接用
- ✅ **处理大数据**：1 亿行聚合秒级返回，足够中型团队
- ✅ **直接读 CSV / Parquet**：和 Zabbix 导出、日志文件无缝衔接
- ✅ **零运维**：没有 server 进程、没有端口、不占服务器

**结论**：传统运维团队（非大数据团队）首推 DuckDB。

---

## 三、整体架构

```
┌─────────────────────────────────────────────────┐
│  源数据层（业务系统导出）                            │
│  zabbix_export.csv / nginx_access.log / tickets   │
└───────────────────┬─────────────────────────────┘
                    │ 每日一次 ETL
                    ▼
┌─────────────────────────────────────────────────┐
│  ODS 层（operational_warehouse.duckdb）           │
│  ods_zabbix_metric / ods_nginx_log / ods_ticket  │
│  原始数据，不动                                    │
└───────────────────┬─────────────────────────────┘
                    │ 清洗、时区统一、单位转换、去重
                    ▼
┌─────────────────────────────────────────────────┐
│  DWD 层                                            │
│  dwd_host_metric_dtl / dwd_alert_dtl / dwd_log_dtl│
│  清洗后的明细，可被任意维度查询                       │
└───────────────────┬─────────────────────────────┘
                    │ 按 主机/日 汇总
                    ▼
┌─────────────────────────────────────────────────┐
│  DWS 层                                          │
│  dws_host_daily / dws_service_daily / dws_alert_daily│
│  主题宽表，分析师常用                                │
└───────────────────┬─────────────────────────────┘
                    │ 计算北极星指标 / 可用率 / SLA
                    ▼
┌─────────────────────────────────────────────────┐
│  ADS 层                                          │
│  ads_availability / ads_slow_query_topn / ads_weekly│
│  报表即用                                        │
└─────────────────────────────────────────────────┘
```

---

## 四、实操：搭一个 5 万行示例数据仓库

下面是 6 步完整流程，每个脚本都能独立跑。**全部源码在文末**。

### 第 1 步：准备模拟数据

`gen_warehouse_data.py` — 生成 50 台主机 × 90 天 × 每小时 1 条 = **10.8 万条** Zabbix 监控明细，5000 条 Nginx 访问日志，200 条告警工单。

```python
"""gen_warehouse_data.py — 生成模拟运维数据"""
import csv, os, random
from datetime import date

random.seed(42)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

# 主机清单
datacenters = ["机房A", "机房B", "机房C"]
biz_lines   = ["交易", "支付", "登录", "内容", "后台"]
hosts = []
with open(os.path.join(DATA, "host_meta.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["host_id", "host_name", "datacenter", "biz_line", "ip"])
    for i in range(1, 51):
        h = f"H{i:05d}"
        hosts.append(h)
        w.writerow([h, f"host_{i:03d}",
                    random.choice(datacenters),
                    random.choice(biz_lines),
                    f"10.0.{(i // 254) + 1}.{(i % 254) + 1}"])
# ... Zabbix / Nginx / 工单生成略，详见脚本
```

**预期产物**：

```
alert_tickets.csv  : 200 行
host_meta.csv      : 50 行
nginx_access.csv   : 5,000 行
zabbix_export.csv  : 432,000 行
```

> 💡 **模拟 vs 生产**：`gen_warehouse_data.py` 只生成模拟数据，方便你本地跑通流程。**真实生产环境**一般不会用这种造数脚本，常见的 ETL 路径有：
>
> - **日志类**：直接读 `/var/log/nginx/*.log`，或经 **ELK**（Filebeat → Logstash → Elasticsearch）汇聚后再抽取。
> - **监控类**：直连 **Zabbix MySQL 数据库**（`history` / `history_uint` 表）拉历史数据；或对接 **Prometheus** 这类时序库的 `remote_write` 接口，用 `mcp` 把指标同步到对象存储再导入 DuckDB。
> - **数据库客户端**：用 **chat2db CLI** 这类工具直连业务 MySQL/Postgres，把监控数据表 `COPY` 到本地。
> - **数据治理**：落 ODS 之前一般还要过一层「字段脱敏 / 空值过滤 / 异常值剔除 / 单位统一」，这一层可以单独写 `etl_clean.py`，把治理规则沉淀成可重跑的脚本。
>
> 这些话题展开讲又是好几篇，**本文点到为止**。如果你对「生产级 ETL 链路搭建」感兴趣，可以单独再出一期，把 ELK + Prometheus + chat2db + DuckDB 串成一个完整 Demo。

### 第 2 步：建 ODS 层（原始数据落盘）

`ods_layer.py` — **不动数据**，原样落盘到 DuckDB。

```python
import duckdb, os
DB = os.path.join(HERE, "operational_warehouse.duckdb")
con = duckdb.connect(DB)

con.execute("CREATE TABLE IF NOT EXISTS ods_host_meta AS "
            "SELECT * FROM read_csv_auto('data/host_meta.csv');")
con.execute("CREATE TABLE IF NOT EXISTS ods_zabbix_metric AS "
            "SELECT * FROM read_csv_auto('data/zabbix_export.csv');")
con.execute("CREATE TABLE IF NOT EXISTS ods_nginx_log AS "
            "SELECT * FROM read_csv_auto('data/nginx_access.csv');")
con.execute("CREATE TABLE IF NOT EXISTS ods_alert_ticket AS "
            "SELECT * FROM read_csv_auto('data/alert_tickets.csv');")
```

> ⚠️ **ODS 层永远不动数据**，只在 DWD 做清洗。这样原始数据可重放、问题可追溯。

### 第 3 步：建 DWD 层（清洗后的明细）

`dwd_layer.py` — **时区统一、单位转换、字段补全**。清洗规则集中在这一层，源数据保持原貌。

**关键清洗动作**：

| 表 | 清洗动作 | 用到的 SQL |
|---|---|---|
| `dwd_host_metric_dtl` | UTC → 北京时间 | `INTERVAL 8 HOUR` |
| `dwd_alert_dtl` | 标准化时间 + 关联主机元数据 | `LEFT JOIN ... USING (host_id)` |
| `dwd_nginx_log_dtl` | 时区处理 + bytes 兜底 | `AT TIME ZONE`、`TRY_CAST` |

```sql
-- 监控明细：UTC → 北京时间
SELECT
    hostid                          AS host_id,
    itemid                          AS metric_name,
    CAST(clock_utc AS TIMESTAMP) + INTERVAL 8 HOUR  AS ts_beijing,
    DATE_TRUNC('hour',
        CAST(clock_utc AS TIMESTAMP) + INTERVAL 8 HOUR) AS ts_hour,
    CAST(value AS DECIMAL(6, 2))    AS metric_value
FROM ods_zabbix_metric;
```

### 第 4 步：建 DWS 层（按维度汇总）

`dws_layer.py` — **按"经常查询的维度"做轻度聚合**：

- 主机 × 日 × 指标（avg / max / p95 / 样本数）
- 告警 × 日 × 机房 × 业务线 × 级别
- 日志 × 日 × URL（请求数 / 5xx 错误数）

```sql
-- DWS：主机 × 日 监控汇总（含 p95）
SELECT
    ts_hour::DATE                              AS stat_date,
    host_id,
    metric_name,
    AVG(metric_value)                          AS avg_value,
    MAX(metric_value)                          AS max_value,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY metric_value) AS p95_value,
    COUNT(*)                                   AS sample_cnt
FROM dwd_host_metric_dtl
GROUP BY ts_hour::DATE, host_id, metric_name;
```

> **核心心法**：DWS 只聚合"经常查的维度"，其它维度查询走 DWD 明细。**不要试图把所有组合都预聚合**。

### 第 5 步：建 ADS 层（报表用）

`ads_layer.py` — **直接喂给周报/月报**：

- `ads_host_availability`：每日单主机可用率
- `ads_top_cpu_host_monthly`：月度 Top10 高 CPU 主机（用 `QUALIFY + ROW_NUMBER` 一行搞定）
- `ads_alert_monthly_summary`：月度告警总览
- `ads_api_availability`：接口 5xx 错误占比

```sql
-- 月度 Top10 高 CPU 主机（DuckDB 特色 QUALIFY 语法）
SELECT
    DATE_TRUNC('month', stat_date) AS stat_month,
    host_id,
    ROUND(AVG(avg_value), 2) AS avg_cpu_pct,
    ROUND(MAX(max_value), 2) AS peak_cpu_pct
FROM dws_host_metric_daily
WHERE metric_name = 'cpu_pct'
GROUP BY DATE_TRUNC('month', stat_date), host_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY DATE_TRUNC('month', stat_date)
    ORDER BY AVG(avg_value) DESC
) <= 10;
```

### 第 6 步：直接出报表

`report_demo.py` — **不再拼 SQL**，所有报表都从 ADS 表 SELECT：

```python
import duckdb
con = duckdb.connect("operational_warehouse.duckdb", read_only=True)

# 报表 1：月度告警总览
df = con.execute("""
    SELECT * FROM ads_alert_monthly_summary
    ORDER BY stat_month DESC, total_alerts DESC
    LIMIT 10
""").df()
```

**实际输出**（部分）：

```
========== 月度告警总览 ==========
stat_month  datacenter  total_alerts  p0_alerts  p1_alerts  avg_recovery_min
2026-01-01          机房A          80         18         23           119.1
2026-01-01          机房B          63         14         10           100.4
2026-01-01          机房C          57         15         13           116.2

========== 1 月 Top10 高 CPU 主机 ==========
host_id  avg_cpu_pct  peak_cpu_pct
H00027        31.50       100.00
H00036        31.21       100.00
H00002        31.17       100.00
...

========== 接口可用率 ==========
url         req_cnt  err5xx_cnt  availability_pct
/api/login      61         21            65.57
/api/order      60         20            66.67
/api/pay        60         14            76.67
```

---

## 五、4 层架构的收益

| 收益 | 详细 |
|---|---|
| 🎯 逻辑清晰 | ODS / DWD / DWS / ADS 各司其职，新人也能接手 |
| 🛡️ 可重跑 | 任何一层错了可以重跑上游，**任何一层都可重建** |
| ⚡ 性能稳定 | ADS 是预聚合的，查询秒级返回 |
| 🔁 可对接 | ADS 可直接灌给 Grafana / DataEase / Excel |
| 📈 可演进 | 小型团队够用，将来上 ClickHouse / Doris 也能平滑迁移 |

---

## 六、几个常见坑

| 坑 | 解决 |
|---|---|
| ODS 太大导致 DWD 跑得慢 | DWD 加分区（按日期 `PARTITION BY`） |
| DWS 聚合耗时太久 | 只聚合"经常查询的维度"，其他走 DWD |
| ADS 表数太多 | 一个业务域一张，比如 `ads_availability` 覆盖所有可用率查询 |
| DuckDB 文件太大 | DuckDB 支持 `VACUUM` 和按列导出 Parquet |
| 时区混乱 | 所有 ODS 存 UTC，所有 DWD 落库前统一转北京时间 |

---

## 七、一键脚本

把上面 6 个文件合并成一个 `build_warehouse.py`，就能一键搭出来：

```bash
pip install duckdb pandas

# 方式一：一键全跑
python build_warehouse.py

# 方式二：分步跑（生产调试推荐）
python gen_warehouse_data.py     # 生成模拟数据
python ods_layer.py              # 建 ODS
python dwd_layer.py              # 建 DWD
python dws_layer.py              # 建 DWS
python ads_layer.py              # 建 ADS
python report_demo.py            # 出报表
```

跑完全部 6 步，会得到一个 `operational_warehouse.duckdb` 文件（约 7-20 MB），里面包含 **4 层架构 + 11 张表 + 可直接喂给周报的现成报表**。

---

## 八、写在最后

DuckDB 给运维团队最大的价值是"**让数据可重放、可追溯、可演进**"。

当你某天发现 ADS 的 P0 告警数和实际工单对不上，你只需要： 
1. 翻 DWD 看清洗规则是否漏了字段；
2. 翻 DWS 看 GROUP BY 维度是否漏了机房；
3. 翻 ODS 看源数据是否完整。

**每一层都有"上一手"，每一步都有"下一手"**——这就是 4 层架构的优雅。

如果你们团队还没建过数仓，今天就动手吧。30 分钟、半杯咖啡、半包烟的成本，换来一套能跑三五年的运维数据底座。

---

> 完整脚本仓库：
> 一句话总结：**DuckDB 让你一个人也能拥有数仓能力。**

_Tags: DuckDB / 运维数仓 / 数据分析 / ODS DWD DWS ADS 