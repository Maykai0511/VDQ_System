import asyncio
import json
import re
import pymysql
from decimal import Decimal
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from ollama import Client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import config

app = FastAPI()

# 跨域配置保持不变
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 初始化 AI 客户端
try:
    ollama_client = Client(host=config.AI_CONFIG["ollama_host"])
    print("✨ Ollama 客户端已就绪")
except Exception as e:
    print(f"❌ Ollama 连接失败: {e}")

mcp_params = StdioServerParameters(command=config.AI_CONFIG["mcp_command"], args=config.AI_CONFIG["mcp_args"])


def universal_clean(obj):
    """递归清洗数据：将 Decimal 转 float，确保 JSON 序列化 100% 成功"""
    if isinstance(obj, list):
        return [universal_clean(i) for i in obj]
    if isinstance(obj, dict):
        return {k: universal_clean(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, str) and obj.replace('.', '', 1).isdigit():
        try:
            return float(obj)
        except:
            return obj
    return obj


# --- 1. AI 聊天接口 (保留所有详细日志 + 按需功能) ---
@app.post("/chat")
async def chat_endpoint(request: Request):
    payload = await request.json()
    user_input = payload.get("message")
    history = payload.get("history", [])
    print(f"\n--- 📩 收到新询问: {user_input} ---")

    try:
        print("🔗 正在启动 MCP Server 并连接数据库...")
        async with stdio_client(mcp_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("connect_db", arguments=config.DB_CONFIG)
                print("✅ MCP & Database 连接成功")

                # 打印 3: 调用 LLM
                print(f"🤖 正在请求 LLM ({config.AI_CONFIG['model']})...")
                messages = [{"role": "system", "content": config.SYSTEM_PROMPT}]
                messages.extend(history[-5:])
                messages.append({"role": "user", "content": user_input})

                response = ollama_client.chat(model=config.AI_CONFIG["model"], messages=messages)
                raw_content = response['message']['content']
                print(f"📝 LLM 原始输出: {raw_content}")

                # 打印 4: 解析指令
                match = re.search(r'\{.*\}', raw_content, re.DOTALL)
                if not match:
                    print("⚠️ 未能在输出中找到 JSON 指令，直接返回文本")
                    return {"answer": raw_content, "action": "none"}

                ai_json = json.loads(match.group())
                action = ai_json.get("action", "none")
                sql = ai_json.get("sql", "")

                # 打印 5: 执行 SQL (如果是趋势分析)
                db_data = []
                if sql:
                    print(f"🛠️  执行 SQL 查询: {sql}")
                    db_result = await session.call_tool("query", arguments={"sql": sql})
                    db_data_raw = db_result.content[0].text if db_result.content else "[]"
                    db_data = universal_clean(json.loads(db_data_raw))
                    print(f"📊 数据库返回数据项: {len(db_data)} 条")

                print(f"🏁 任务完成，Action: {action}，正在返回前端...")
                return {
                    "answer": ai_json.get("answer", "解析完成"),
                    "action": action,
                    "dimension": ai_json.get("dimension", "stock"),
                    "chart_data": db_data,
                    "sql": sql
                }

    except Exception as e:
        print(f"❌ 运行报错: {str(e)}")
        return {"answer": f"系统内部错误: {str(e)}", "action": "none"}


# --- 2. WebSocket 实时监控 (支持按需启动和维度切换) ---
@app.websocket("/ws/stats/{dimension}")
async def websocket_stats(websocket: WebSocket, dimension: str):
    await websocket.accept()
    print(f"📡 [WebSocket] 前端大屏已上线，监控维度: {dimension}")
    try:
        while True:
            conn = None
            try:
                conn = pymysql.connect(**config.DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
                with conn.cursor() as cursor:
                    # 动态切换查询字段
                    target_field = "price" if dimension == "price" else "stock"
                    sql = f"SELECT name, {target_field} as val FROM vegetables ORDER BY {target_field} DESC LIMIT 6"
                    cursor.execute(sql)
                    raw_data = cursor.fetchall()

                # 清洗并发送
                cleaned_data = universal_clean(raw_data)
                await websocket.send_json(cleaned_data)

            except Exception as db_e:
                print(f"⚠️ [WebSocket] 循环中出错: {db_e}")
            finally:
                if conn: conn.close()

            await asyncio.sleep(2)  # 2秒刷新一次

    except WebSocketDisconnect:
        print(f"🔌 [WebSocket] 连接正常断开 (维度: {dimension})")
    except Exception as e:
        print(f"❌ [WebSocket] 致命异常: {e}")

@app.get("/")
async def read_index():
    return FileResponse('index.html') # 确保 index.html 在同级目录下