import asyncio
import json
import pymysql
from aiokafka import AIOKafkaConsumer

# 数据库配置（请填写你自己的密码）
DB_CONFIG = {
    "host": "localhost", "user": "root", "password": "root",
    "database": "vdq_system_db", "autocommit": True
}


async def consume():
    consumer = AIOKafkaConsumer(
        'veg_data', bootstrap_servers='localhost:9092', group_id="flink-group"
    )
    await consumer.start()
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("🌊 2026版 异步流处理引擎已启动...")
    try:
        async for msg in consumer:
            data = json.loads(msg.value.decode('utf-8'))

            # --- 模拟 Flink 逻辑：价格纠偏与入库 ---
            if data['price'] < 0.5: continue  # 过滤错误低价

            sql = """INSERT INTO vegetables (name, price, stock) 
                     VALUES (%s, %s, %s) 
                     ON DUPLICATE KEY UPDATE price=%s, stock=%s"""
            cursor.execute(sql, (data['name'], data['price'], data['stock'], data['price'], data['stock']))
            print(f"✅ 流处理并入库: {data['name']} (实时价格: {data['price']})")
    finally:
        await consumer.stop()
        conn.close()


if __name__ == "__main__":
    asyncio.run(consume())