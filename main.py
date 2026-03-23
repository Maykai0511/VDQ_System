import asyncio
import json
import re
from ollama import Client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- 1. 定义系统提示词 (Schema 地图) ---
SYSTEM_PROMPT = """你是一个专业的蔬菜店数据分析助手。
必须严格遵守以下数据库表结构（Schema）来编写 SQL：

1. 表名: vegetables
   - 字段: id, name (蔬菜名称), stock (库存), price (单价)

2. 表名: veg_records
   - 字段: id, veg_id (关联vegetables.id), record_type (记录类型: SALE(销售), RESTOCK(进货), PRICE_CHANGE(调价), LOSS(损耗)), 
     quantity_change (变动数量), current_price (当时单价), total_amount (总金额), record_time

查询要求：
- 如果用户问库存，请查询 vegetables 表。
- 蔬菜库存的单位是公斤，价格的单位是元。
- 必须使用正确的字段名，例如：蔬菜名是 'name' 而不是 'product_name'。
- 只能输出 JSON 格式：{"action": "query", "sql": "SELECT ..."} 
- 不要输出任何多余的解释文字。"""

# --- 配置 ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "vdq_system_db"
}
MODEL_NAME = "qwen3:8b"

ollama_client = Client(host='http://localhost:11434', timeout=300.0)

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@f4ww4z/mcp-mysql-server"]
)


async def run_chat():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ MCP 核心已启动")

            # 自动连接数据库
            try:
                await session.call_tool("connect_db", arguments=DB_CONFIG)
                print("✅ 数据库连接成功！")
            except Exception as e:
                print(f"❌ 连接数据库失败: {e}")
                return

            user_input = "现在西红柿还有多少库存？"
            print(f"🚀 用户提问: {user_input}")

            try:
                # --- 2. 在这里加入 SYSTEM_PROMPT ---
                response = ollama_client.chat(model=MODEL_NAME, messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},  # 注入灵魂
                    {'role': 'user', 'content': user_input},
                ])

                content = response['message']['content']
                print(f"🤖 模型生成的指令: {content}")

                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    sql = json.loads(match.group())["sql"]
                    print(f"🛠️  正在执行修正后的 SQL: {sql}")

                    # 执行查询
                    db_result = await session.call_tool("query", arguments={"sql": sql})
                    data_str = db_result.content[0].text

                    # 让模型根据结果说人话
                    final_res = ollama_client.chat(model=MODEL_NAME, messages=[
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': f"查询结果是：{data_str}\n请结合此结果回答用户：{user_input}"},
                    ])
                    print(f"\n✨ AI 最终回答: {final_res['message']['content']}")

            except Exception as e:
                print(f"❌ 运行异常: {e}")


if __name__ == "__main__":
    asyncio.run(run_chat())