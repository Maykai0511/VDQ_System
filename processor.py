import asyncio
import json
import pymysql
import time
from aiokafka import AIOKafkaConsumer

# --- 配置（请根据实际情况修改密码和数据库名） ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "vdq_system_db",
    "autocommit": False  # 2026年毕设：必须关闭自动提交，使用显式事务
}
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
KAFKA_TOPIC = 'veg_data'


async def process_stream():
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="flink-processor-group"
    )
    await consumer.start()

    # 建立数据库连接
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("🌊 2026版 事务性流处理引擎已启动，正在监听 Kafka...")

    try:
        async for msg in consumer:
            data = json.loads(msg.value.decode('utf-8'))
            veg_name = data['name']
            new_price = data['price']
            new_stock = data['stock']

            # --- Flink 算子：异常值清洗 (毕设保留项) ---
            if new_price < 0.5: continue

            print(f"📡 收到数据: {veg_name} | 价格: {new_price} | 库存: {new_stock}")

            try:
                # --- 1. 开启事务 (事务性写库的起点) ---
                conn.begin()

                # --- 2. 处理 vegetables 表 (当前状态) ---
                # 先尝试获取旧数据，用于判断记录类型
                cursor.execute("SELECT id, price, stock FROM vegetables WHERE name = %s", (veg_name,))
                old_data = cursor.fetchone()

                if old_data:
                    veg_id, old_price, old_stock = old_data
                    # 更新当前数据
                    sql_update = "UPDATE vegetables SET price=%s, stock=%s WHERE id=%s"
                    cursor.execute(sql_update, (new_price, new_stock, veg_id))

                    # --- 3. 处理 veg_records 表 (流水记录) ---
                    # 3.a 智能判断记录类型 (毕设亮点：逻辑推理)
                    if new_price != old_price:
                        record_type = 'PRICE_CHANGE'
                        quantity_change = 0  # 调价不涉及数量变化
                    elif new_stock > old_stock:
                        record_type = 'RESTOCK'
                        quantity_change = new_stock - old_stock
                    else:
                        # 其他情况暂不记录，保持流水清晰
                        record_type = None

                    if record_type:
                        sql_record = """INSERT INTO veg_records 
                                       (veg_id, record_type, quantity_change, current_price, total_amount, record_time)
                                       VALUES (%s, %s, %s, %s, %s, %s)"""
                        total_amount = new_price * quantity_change if quantity_change > 0 else 0
                        cursor.execute(sql_record, (veg_id, record_type, quantity_change, new_price, total_amount,
                                                    time.strftime("%Y-%m-%d %H:%M:%S")))

                else:
                    # 2026年新表初始化逻辑：新蔬菜入库，默认为RESTOCK
                    sql_init = "INSERT INTO vegetables (name, price, stock) VALUES (%s, %s, %s)"
                    cursor.execute(sql_init, (veg_name, new_price, new_stock))
                    veg_id = cursor.lastrowid  # 获取刚插入的 ID

                    sql_record_init = """INSERT INTO veg_records 
                                       (veg_id, record_type, quantity_change, current_price, total_amount, record_time)
                                       VALUES (%s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql_record_init, (
                    veg_id, 'RESTOCK', new_stock, new_price, new_price * new_stock, time.strftime("%Y-%m-%d %H:%M:%S")))

                # --- 4. 提交事务 (保证原子性) ---
                conn.commit()
                print(f"✅ 事务处理完成: {veg_name}")

            except Exception as transaction_err:
                # 出现任何错误，立刻回滚，保证数据一致性
                conn.rollback()
                print(f"❌ 事务回滚: {veg_name} | 错误: {transaction_err}")

    except Exception as e:
        print(f"❌ 系统异常: {e}")
    finally:
        await consumer.stop()
        conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(process_stream())
    except KeyboardInterrupt:
        print("\n处理器已停止。")