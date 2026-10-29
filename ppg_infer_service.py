import msgpack
import pika

from utilis import add_ppg_data

RABBITMQ_HOST = "127.0.0.1"
RABBITMQ_PORT = 5672
RABBITMQ_USERNAME = "admin"
RABBITMQ_PASSWORD = "ccnu@1290"
QUEUE_NAME = "ppg_infer"


def connect_rabbitmq():
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=30
        )
    )
    return connection


def callback(ch, method, properties, body):

    try:
        data = msgpack.unpackb(body, raw=False)
        # print(f"[PPG-INFER] 解包成功, type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'NOT_DICT'}")


        if not isinstance(data, dict):
            raise ValueError("msgpack 解包后不是 dict")

        # 直接喂给新版 add_ppg_data
        add_ppg_data(data)

        # print(f"[PPG-INFER] callback 处理完成")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[PPG-INFER] 处理失败: {e}")
        try:
            print(f"[PPG-INFER] 原始 body 前200字节: {body[:200]}")
        except Exception:
            pass
        ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    connection = connect_rabbitmq()
    channel = connection.channel()

    result = channel.queue_declare(queue=QUEUE_NAME, durable=True)
    print(f"[PPG-INFER] 队列 '{QUEUE_NAME}' 已声明")
    print(f"[PPG-INFER] 启动前：消息数={result.method.message_count}")
    print(f"[PPG-INFER] 启动前：消费者数={result.method.consumer_count}")

    channel.basic_qos(prefetch_count=50)

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback,
        auto_ack=False
    )

    # 再查一次，看 consumer 是否已经注册
    result2 = channel.queue_declare(queue=QUEUE_NAME, durable=True)
    print(f"[PPG-INFER] 注册 consume 后：消息数={result2.method.message_count}")
    print(f"[PPG-INFER] 注册 consume 后：消费者数={result2.method.consumer_count}")

    print(f"[PPG-INFER] Waiting for messages from queue '{QUEUE_NAME}'...")
    channel.start_consuming()


if __name__ == "__main__":
    main()