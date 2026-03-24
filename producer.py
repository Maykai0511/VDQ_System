import asyncio
import json
import random
import time
from aiokafka import AIOKafkaProducer

async def produce():
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    await producer.start()
    vegs = ["西红柿", "大白菜", "青椒", "西兰花", "土豆", "胡萝卜"]
    try:
        print("🚀 蔬菜数据采集器启动...")
        while True:
            data = {
                "name": random.choice(vegs),
                "price": round(random.uniform(2.0, 15.0), 2),
                "stock": random.randint(50, 500),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            await producer.send_and_wait("veg_data", data)
            print(f"📡 已推送到 Kafka: {data}")
            await asyncio.sleep(2)  # 每 2 秒采集一次
    finally:
        await producer.stop()

if __name__ == "__main__":
    asyncio.run(produce())