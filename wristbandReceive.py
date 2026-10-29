import pika
import msgpack
import json
import datetime
from utilis import add_ppg_data

# 连接到 RabbitMQ 服务器
def connect_rabbitmq():
    # 使用用户名和密码连接
    credentials = pika.PlainCredentials('admin', 'ccnu@1290')  # 根据实际的用户名和密码
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='127.0.0.1', credentials=credentials))
    return connection

def print_message(message):
    """
    解析并格式化输出手环的MsgPack数据
    :param message: 原始的手环数据字典
    """
    try:
        # 1. 提取基础信息
        student_id = message.get('student_id', '未定义')
        data_type = message.get('data_type', '未定义')
        data = message.get('data', [])

        # 2. 解析data中的各个数据项（按顺序）
        # 初始化默认值，防止数据长度不足导致报错
        timestamp_ms = None
        sampling_freq = None
        raw_calib_data = []
        time_intervals = []
        sensor_data = []

        if len(data) >= 5:
            timestamp_ms = data[0]
            sampling_freq = data[1]
            raw_calib_data = data[2]
            time_intervals = data[3]
            sensor_data = data[4]

        # 3. 时间戳转换：毫秒级时间戳 -> 可读的本地时间
        if timestamp_ms is not None:
            # 转换为秒级时间戳（除以1000），再转为datetime对象
            local_time = datetime.datetime.fromtimestamp(timestamp_ms / 1000.0)
            time_str = local_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # 保留毫秒
        else:
            time_str = '无效时间戳'

        # 4. 格式化输出所有信息
        print("=" * 60)
        print(f"【基础信息】")
        print(f"学生ID：{student_id}")
        print(f"数据类型：{data_type}")
        print(f"采集时间：{time_str}")
        print(f"手环采样频率：{sampling_freq} Hz（每秒采集{sampling_freq}次）")

        print(f"\n【传感器原始校准数据（共{len(raw_calib_data)}组）】")
        print("格式：[硬件原始计数值, 校准偏移值]")
        for idx, item in enumerate(raw_calib_data, 1):
            print(f"  第{idx}组：{item}")

        print(f"\n【采样点时间间隔（共{len(time_intervals)}个）】")
        print(f"单位：秒（s），所有间隔值：{time_intervals}")
        print(f"说明：每个值表示连续两个采样点的时间差，此处均为{time_intervals[0] if time_intervals else 0}s")

        print(f"\n【多维度传感器数据（共{len(sensor_data)}组）】")
        print("格式：[加速度X轴(m/s²), 加速度Y轴(m/s²), 加速度Z轴(m/s²)]")
        for idx, item in enumerate(sensor_data, 1):
            print(f"  第{idx}组：{item}")
        print("=" * 60)

    except Exception as e:
        print(f"解析数据时发生错误：{str(e)}")
        print(f"原始数据：{message}")
# 消息的回调函数
def callback(ch, method, properties, body):
    # print("Received a message.")

    # 判断消息类型
    if properties.content_type == 'application/json':
        # 处理JSON数据
        print("Received JSON message:")
        try:
            message = json.loads(body.decode())
            print(message)
        except Exception as e:
            print(f"Failed to decode JSON: {e}")

    elif properties.content_type == 'application/msgpack':
        # 处理 msgpack 数据
        # print("Received msgpack message:")
        try:
            unpacked_data = msgpack.unpackb(body)

            # 打印原始数据
            # print(unpacked_data)

            # 打印原始数据解析消息
            # print_message(unpacked_data)

            #划入滑动窗口进行存储
            add_ppg_data(unpacked_data)

        except Exception as e:
            print(f"Failed to unpack msgpack: {e}")

    else:
        print("Received unknown content type:", properties.content_type)

    # print("------------------------------------")


# 设置连接和频道
def setup_rabbitmq_consumer():
    connection = connect_rabbitmq()
    channel = connection.channel()

    # 声明一个队列
    queue_name = 'wristband'  # 根据手环数据发送的队列名来设置
    channel.queue_declare(queue=queue_name, durable=True)

    # 绑定队列到交换机 (这个配置取决于你 RabbitMQ 交换机的设置)
    exchange_name = 'amq.topic'  # 你需要确认你使用的交换机和路由键
    routing_key = 'student.*.wristband'  # 根据你的路由键设置
    channel.queue_bind(queue=queue_name, exchange=exchange_name, routing_key=routing_key)

    # 启动消费者
    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)

    print(f"Waiting for messages from queue {queue_name}. To exit press CTRL+C.")

    # 开始消费消息
    channel.start_consuming()


if __name__ == "__main__":
    setup_rabbitmq_consumer()
