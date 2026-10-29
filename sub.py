import pika
import msgpack
from datetime import datetime
from typing import List, Dict, Any
# import utilis
# from LinkPostgreSQL import connect_postgres, create_or_get_metadata
from functools import partial
from datastream_bridge import  deserialize_bcg_msgpack,deserialize_mmwave_msgpack
class EEGData:
    def __init__(self, timestamp: int, data_type: str):
        self.timestamp = timestamp  # 毫秒时间戳
        self.type = data_type  # 数据类型标识


class EEGSensorData(EEGData):
    def __init__(self, timestamp: int, adc_status: bytes, channel_data: List[float], trigger: float):
        super().__init__(timestamp, "SensorData")
        self.adc_status = adc_status  # bytes状态信息
        self.channel_data = channel_data  # 24通道浮点数据
        self.trigger = trigger  # 触发信号

    def __repr__(self):
        dt = datetime.fromtimestamp(self.timestamp / 1000)
        return (
            f"EEGSensorData(timestamp={dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, "
            f"adcStatus={int.from_bytes(self.adc_status, 'big')}, "
            f"channelData={self.channel_data}, trigger={self.trigger})"
        )


class EEGEventData(EEGData):
    def __init__(self, timestamp: int, code: int, message: Dict[str, Any]):
        super().__init__(timestamp, "EventData")
        self.code = code  # 事件代码
        self.message = message  # 事件消息字典

    def __repr__(self):
        dt = datetime.fromtimestamp(self.timestamp / 1000)
        return (
            f"EEGEventData(timestamp={dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, "
            f"code={self.code}, message={self.message})"
        )


# 序列化逻辑
def serialize_sensor(obj: EEGSensorData) -> bytes:
    return msgpack.packb([
        obj.timestamp,
        obj.adc_status,
        obj.channel_data,
        obj.trigger
    ])


def serialize_event(obj: EEGEventData) -> bytes:
    if obj.code in {1, 9}:
        msg = {k: str(v) for k, v in obj.message.items()}
    elif obj.code == 10:
        msg = {k: int(v) for k, v in obj.message.items()}
    else:
        msg = None
    return msgpack.packb([
        obj.timestamp,
        obj.code,
        msg
    ])


# 反序列化逻辑
def deserialize_sensor(data) -> EEGSensorData:
    # unpacked = msgpack.unpackb(data)
    return EEGSensorData(
        timestamp=data[0],
        adc_status=data[1],
        channel_data=data[2],
        trigger=data[3]
    )


def deserialize_event(data: bytes) -> EEGEventData:
    unpacked = msgpack.unpackb(data)
    msg = {}

    if unpacked[2] is not None:
        if unpacked[1] in {1, 9}:
            msg = {k.decode(): v.decode() for k, v in unpacked[2].items()}
        elif unpacked[1] == 10:
            msg = {k.decode(): v for k, v in unpacked[2].items()}

    return EEGEventData(
        timestamp=unpacked[0],
        code=unpacked[1],
        message=msg
    )

import pika
import msgpack
from datetime import datetime
from zoneinfo import ZoneInfo   # Python 3.9+

def format_ts_ms(ts_ms):
    """
    毫秒时间戳 -> 北京时间字符串
    """
    try:
        ts_ms = int(ts_ms)
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=ZoneInfo("Asia/Shanghai"))
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except Exception as e:
        return f"invalid_timestamp({ts_ms!r}, err={e})"


def callback(ch, method, properties, body):
    print("routing_key:", method.routing_key)
    print("content_type:", properties.content_type)

    print("------------------------------------")

def callback_bcg(ch, method, properties, body):
    try:
        packet = deserialize_bcg_msgpack(body)

        print("收到 BCG 数据")
        print("student_id:", packet.student_id)
        print("data_type:", packet.data_type)
        print("timestamp:", packet.timestamp)
        print("source:", packet.source)
        print("sampling_rate:", packet.sampling_rate)
        print("start_timestamp:", packet.start_timestamp)
        print("end_timestamp:", packet.end_timestamp)
        print("heart_rate:", packet.heart_rate)
        print("respiratory_rate:", packet.respiratory_rate)
        print("heart_waveform 长度:", len(packet.heart_waveform))
        print("resp_waveform 长度:", len(packet.resp_waveform))


    except Exception as e:
        print("BCG 解包失败:", e)
        print("raw body:", body[:200])

    print("-" * 40)


def callback_ppg(ch, method, properties, body):
    print(f"[PPG] {method.routing_key} -> {body}")
    # PPG 处理逻辑

def callback_rppg(ch, method, properties, body):
    print(f"[RPPG] {method.routing_key} -> {body}")
    # RPPG 处理逻辑

def callback_mmwav(ch, method, properties, body):
    try:
        packet = deserialize_mmwave_msgpack(body)

        # print("收到 mmWav 数据")
        # print("routing_key:", method.routing_key)
        # print("student_id:", packet.student_id)
        # print("data_type:", packet.data_type)
        # print("timestamp:", packet.timestamp)
        # print("source:", packet.source)
        # print("sampling_rate:", packet.sampling_rate)
        # print("start_timestamp:", packet.start_timestamp)
        # print("end_timestamp:", packet.end_timestamp)
        # print("heart_rate:", packet.heart_rate)
        # print("respiratory_rate:", packet.respiratory_rate)
        # print("fatigue_state:", packet.fatigue_state)
        # print("body_move:", packet.body_move)
        # print("distance:", packet.distance)
        # print("occupancy:", packet.occupancy)
        # print("heart_wave_filtered 长度:", len(packet.heart_wave_filtered))
        # print("breath_wave_filtered 长度:", len(packet.breath_wave_filtered))
        #
        # # 想看前几个点可以打开
        # print("heart_wave_filtered 前5个点:", packet.heart_wave_filtered[:5])
        # print("breath_wave_filtered 前5个点:", packet.breath_wave_filtered[:5])

    except Exception as e:
        print("mmWav 解包失败:", e)
        print("raw body:", body[:200])

    print("-" * 40)


def main():

    # 建立与 RabbitMQ 服务器的连接
    credentials = pika.PlainCredentials('admin', 'ccnu@1290')
    # 连接到服务器上
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='127.0.0.1', credentials=credentials))

    channel = connection.channel()

    # 4 个队列都要先声明
    channel.queue_declare(queue='bcg', durable=True)
    channel.queue_declare(queue='wristband', durable=True)
    channel.queue_declare(queue='wristbandemotion', durable=True)
    channel.queue_declare(queue='rppg', durable=True)
    channel.queue_declare(queue='mmwave', durable=True)

    # 绑定到 topic exchange
    channel.queue_bind(queue='bcg', exchange='amq.topic', routing_key='student.*.bcg')
    channel.queue_bind(queue='wristband', exchange='amq.topic', routing_key='student.*.wristband')
    channel.queue_bind(queue='wristbandemotion', exchange='amq.topic', routing_key='student.*.wristbandemotion')
    channel.queue_bind(queue='rppg', exchange='amq.topic', routing_key='student.*.rppg')
    channel.queue_bind(queue='mmwave', exchange='amq.topic', routing_key='student.*.mmwav')

    # 注册 4 个消费者
    channel.basic_consume(queue='bcg', on_message_callback=callback, auto_ack=True)
    channel.basic_consume(queue='wristbandemotion', on_message_callback=callback, auto_ack=True)
    channel.basic_consume(queue='wristband', on_message_callback=callback, auto_ack=True)
    channel.basic_consume(queue='rppg', on_message_callback=callback, auto_ack=True)
    channel.basic_consume(queue='mmwave', on_message_callback=callback, auto_ack=True)

    print('Waiting for messages. To exit press CTRL+C')

    try:
        # 开始监听
        channel.start_consuming()
    except KeyboardInterrupt:
        print('Exiting...')
        channel.stop_consuming()

    connection.close()


if __name__ == "__main__":
    main()
