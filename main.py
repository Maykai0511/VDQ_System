import asyncio
import json
import re
from ollama import Client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- 系统提示词保持不变 ---
SYSTEM_PROMPT = """你是一个专业的蔬菜店智能分析助手。
必须严格遵守以下数据库表结构（Schema）来编写 SQL：

1. 表名: vegetables
   - 字段: id, name (蔬菜名称), stock (当前库存 单位：千克), price (当前单价 单位：元)

2. 表名: veg_records
   - 字段: id, veg_id (关联vegetables.id), record_type (记录类型: SALE, RESTOCK, PRICE_CHANGE, LOSS), 
     quantity_change (变动数量), current_price (当时单价), total_amount (总金额), record_time

查询规范：
- [库存/价格]: 问当前状态，请查询 vegetables 表。
- [趋势/历史]: 问价格变化、进货历史等，必须联查 vegetables 和 veg_records 表。
- [可视化规则]: 如果用户问“趋势”、“变化情况”等需要画图的问题，你必须在返回的 JSON 中额外包含 "chart_type": "line" 或 "bar"。

只能输出 JSON：{"action": "query", "sql": "SELECT ...", "chart_type": "none/line/bar"} 
不要输出任何多余的解释文字。"""

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
                print("✅ 数据库连接成功！输入 'exit' 退出聊天。")
            except Exception as e:
                print(f"❌ 连接数据库失败: {e}")
                return

            # --- 2026版 毕设亮点：上下文记忆链 ---
            chat_history = []

            while True:
                user_input = input("\n👤 您好，请问有什么可以帮您？ (输入 exit 退出): ").strip()

                if not user_input:
                    continue
                if user_input.lower() in ['exit', 'quit']:
                    print("👋 再见！系统正在关闭上下文链...")
                    break

                # 模拟上下文：将新问题加入历史
                chat_history.append({'role': 'user', 'content': user_input})

                print(f"🚀 正在调用本地 LLM 进行语义解析...")

                try:
                    # --- 第一步：Text-to-SQL (携带历史上下文) ---
                    # 2026年技巧：只把 SYSTEM_PROMPT 和最后几轮对话传给模型，避免 Token 爆炸
                    messages_to_send = [{'role': 'system', 'content': SYSTEM_PROMPT}] + chat_history[-5:]

                    response = ollama_client.chat(model=MODEL_NAME, messages=messages_to_send)
                    content = response['message']['content']

                    # JSON 健壮匹配
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if not match:
                        print(f"🤖 AI 回复: {content} (未生成查询指令)")
                        # 将 AI 的解释性回复也加入历史，保持上下文连贯
                        chat_history.append({'role': 'assistant', 'content': content})
                        continue

                    # 解析并执行 SQL
                    try:
                        sql_json = json.loads(match.group())
                        sql = sql_json.get("sql", "")
                        chart_type = sql_json.get("chart_type", "none")  # 2026年毕设亮点：可视化预留标志位
                        print(f"🛠️  执行标准 SQL: {sql}")

                        if chart_type != "none":
                            print(f"📊 [可视化预留] 识别到图表需求：{chart_type}")

                        db_result = await session.call_tool("query", arguments={"sql": sql})
                        # 获取数据
                        data_str = db_result.content[0].text if db_result.content else "无查询结果"

                        # 2026年技巧：如果数据太长，只传给模型摘要，原数据留给前端画图
                        if len(data_str) > 1000:
                            data_for_llm = data_str[:1000] + "... (数据已截断，用于生成自然语言摘要)"
                        else:
                            data_for_llm = data_str

                    except Exception as sql_err:
                        data_str = f"数据库查询出错: {sql_err}"
                        data_for_llm = data_str

                    # --- 第二步：自然语言回答 (携带查询结果) ---
                    # 这里不需要传递全部历史，只需告诉模型当前问题和当前结果
                    interpret_prompt = "你是一个亲切的数据分析师。根据数据库返回的数据，用自然语言回答用户的问题。如果数据表明适合画图，提及一句'已为您预留可视化接口'。"
                    final_res = ollama_client.chat(model=MODEL_NAME, messages=[
                        {'role': 'system', 'content': interpret_prompt},
                        {'role': 'user', 'content': f"用户问：{user_input}\n查询结果：{data_for_llm}"},
                    ])

                    print("-" * 30)
                    print(f"✨ AI (携带上下文): {final_res['message']['content']}")
                    if chart_type != "none":
                        print(f"📈 [可视化数据预览]: {data_str[:200]}...")  # 前端会将这串 JSON 解析为 ECharts
                    print("-" * 30)

                    # 将 AI 的自然语言回答加入历史
                    chat_history.append({'role': 'assistant', 'content': final_res['message']['content']})

                except Exception as e:
                    print(f"❌ 对话逻辑异常: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        print("\n对话已手动终止。")