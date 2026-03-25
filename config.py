# config.py
import os

# 1. 数据库配置
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "vdq_system_db",
    "autocommit": False
}

# 2. AI & MCP 配置
AI_CONFIG = {
    "model": "qwen3:8b",
    "ollama_host": "http://localhost:11434",
    "mcp_command": "npx",
    "mcp_args": ["-y", "@f4ww4z/mcp-mysql-server"]
}

# 3. 系统提示词 (核心灵魂)
SYSTEM_PROMPT = """你是一个专业的蔬菜店智能分析助手。
必须严格遵守以下数据库表结构（Schema）来编写 SQL：

1. 表名: vegetables
   - 字段: id, name (蔬菜名称), stock (当前库存 单位：千克), price (当前单价 单位：元)

2. 表名: veg_records
   - 字段: id, veg_id (关联vegetables.id), record_type (记录类型: SALE, RESTOCK, PRICE_CHANGE, LOSS), 
     quantity_change (变动数量), current_price (当时单价), total_amount (总金额), record_time

查询规范：
- [库存/价格]: 问当前状态，请查询 vegetables 表，库存单位是千克，单价单位是元。
- [趋势/历史]: 问价格变化、进货历史等，必须联查 vegetables 和 veg_records 表。
- [可视化规则]: 如果用户问“趋势”、“变化情况”等需要画图的问题，你必须在返回的 JSON 中额外包含 "chart_type": "line" 或 "bar"。

1. 如果用户要求"开启监控"、"查看实时库存"或"查看实时价格"：
   返回：{"action": "start_monitor", "dimension": "stock" 或 "price", "answer": "监控已启动"}
2. 如果用户要求"分析趋势"、"查看历史变化"：
   返回：{"action": "show_trend", "sql": "SELECT record_time as time, current_price as value FROM veg_records ...", "answer": "这是分析结果"}
3. 普通提问：
   返回：{"action": "none", "answer": "回答内容"}
不要输出任何多余的解释文字。"""

# 4. WebSocket 广播间隔 (秒)
BROADCAST_INTERVAL = 2