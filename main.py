import asyncio
import json
import re
from ollama import Client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- 系统提示词保持不变 ---
SYSTEM_PROMPT = """你是一个专业的蔬菜店数据分析助手。
必须严格遵守以下数据库表结构来编写 SQL：
1. 表名: vegetables (字段: id, name, stock, price)
2. 表名: veg_records (字段: id, veg_id, record_type, quantity_change, current_price, total_amount, record_time)
查询要求：
- 如果用户问库存，查询 vegetables。
- 只能输出 JSON：{"action": "query", "sql": "SELECT ..."}
- 不要输出多余文字。"""

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",  # 记得确认这里的密码是否为你设置的 'root'
    "database": "vdq_system_db"
}
MODEL_NAME = "qwen3:8b"  # 既然是 2026 年，Qwen3 绝对是国产之光

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
                print("✅ 数据库连接成功！输入 'exit' 或 'quit' 退出聊天。")
            except Exception as e:
                print(f"❌ 连接数据库失败: {e}")
                return

            # --- 开启持续对话循环 ---
            while True:
                user_input = input("\n👤 你想问什么？ (输入 exit 退出): ").strip()

                if not user_input:
                    continue
                if user_input.lower() in ['exit', 'quit']:
                    print("👋 再见！期待下次为您服务。")
                    break

                print(f"🚀 正在分析问题: {user_input}")

                try:
                    # 第一步：生成 SQL
                    response = ollama_client.chat(model=MODEL_NAME, messages=[
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_input},
                    ])

                    content = response['message']['content']

                    # 使用更健壮的 JSON 匹配
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if not match:
                        print(f"🤖 AI 回复: {content} (未生成有效查询语句)")
                        continue

                    # 解析并执行 SQL
                    try:
                        sql_json = json.loads(match.group())
                        sql = sql_json.get("sql", "")
                        print(f"🛠️  执行 SQL: {sql}")

                        db_result = await session.call_tool("query", arguments={"sql": sql})
                        # 获取工具返回的内容
                        data_str = db_result.content[0].text if db_result.content else "无查询结果"
                    except Exception as sql_err:
                        data_str = f"数据库查询出错: {sql_err}"

                    # 第二步：生成人类可读的回答
                    final_res = ollama_client.chat(model=MODEL_NAME, messages=[
                        {'role': 'system', 'content': "根据数据库返回的内容，用亲切自然的口吻回答用户。"},
                        {'role': 'user', 'content': f"用户问：{user_input}\n查询结果：{data_str}"},
                    ])

                    print("-" * 30)
                    print(f"✨ AI: {final_res['message']['content']}")
                    print("-" * 30)

                except Exception as e:
                    print(f"❌ 对话逻辑异常: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        print("\n程序已手动终止。")