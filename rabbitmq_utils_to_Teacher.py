import time
import msgpack
import paho.mqtt.client as mqtt
import random
from typing import Optional

# ===================== 配置项 =====================
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USERNAME = "admin"
MQTT_PASSWORD = "ccnu@1290"

# 全局变量：标记MQTT是否连接成功
mqtt_connected = False
mqtt_client = None

"""
mock情绪标签
"""
emotionlist = {
    1: "高兴",
    2: "难过",
    3: "中性",
}


# ===================== MQTT客户端初始化 =====================
def init_mqtt_client():
    global mqtt_client, mqtt_connected

    client = mqtt.Client(
        client_id="emotion_recognizer_multi",
        protocol=mqtt.MQTTv311
    )
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    def on_connect(client, userdata, flags, rc, properties=None):
        global mqtt_connected
        if rc == 0:
            mqtt_connected = True
            print("MQTT连接成功")
        else:
            mqtt_connected = False
            print(f"MQTT连接失败，错误码：{rc}")

    def on_disconnect(client, userdata, rc):
        global mqtt_connected
        mqtt_connected = False
        print(f"MQTT断开连接，错误码：{rc}，正在尝试重连...")
        try:
            client.reconnect()
        except Exception as e:
            print(f"MQTT重连失败：{e}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    mqtt_client = client

    timeout = 5
    start_time = time.time()
    while not mqtt_connected and (time.time() - start_time) < timeout:
        time.sleep(0.1)

    if not mqtt_connected:
        raise ConnectionError(f"MQTT连接超时（{timeout}秒），请检查服务器配置")

    return client


# 初始化客户端
mqtt_client = init_mqtt_client()


def _publish_msgpack(topic: str, payload_dict: dict, success_text: str):
    global mqtt_connected, mqtt_client

    if not mqtt_connected or mqtt_client is None:
        print("MQTT未连接，无法发送消息")
        return

    try:
        data_bytes = msgpack.packb(payload_dict, use_bin_type=True, strict_types=True)
        result = mqtt_client.publish(topic, payload=data_bytes, qos=1, retain=False)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(success_text)
        else:
            print(f"消息发送失败，错误码：{result.rc}")
    except Exception as e:
        print(f"发送消息时出现异常：{str(e)}")


# ===================== 发送识别结果的函数 =====================
def send_ppgemotion_result(pred_name, student_uid):
    """
    发送PPG模型识别的情绪
    """
    if student_uid is None or str(student_uid).strip() == "":
        print("send_ppgemotion_result 缺少 student_uid，取消发送")
        return

    student_uid = str(student_uid).strip()

    emotion_detail = {
        "pred_name": str(pred_name),
        "timestamp": int(time.time() * 1000),
        "source": "ppg_emotion_recognizer"
    }

    emotion_data = {
        "student_id": student_uid,
        "data_type": "wristbandemotion",
        "data": emotion_detail
    }

    topic = f"student/{student_uid}/wristbandemotion"
    _publish_msgpack(
        topic=topic,
        payload_dict=emotion_data,
        success_text=f"PPG情绪结果发送成功：student_id={student_uid}, pred={pred_name}, topic={topic}"
    )


def send_eegemotion_result(student_uid: Optional[str] = None):
    """
    发送EEG模型识别的情绪（这里仍然是mock）
    """
    if student_uid is None or str(student_uid).strip() == "":
        print("send_eegemotion_result 缺少 student_uid，取消发送")
        return

    student_uid = str(student_uid).strip()
    index = random.randint(1, 3)

    emotion_detail = {
        "pred_class": int(index),
        "pred_name": str(emotionlist[index]),
        "timestamp": int(time.time() * 1000),
        "source": "eeg_emotion_recognizer"
    }

    emotion_data = {
        "student_id": student_uid,
        "data_type": "eegemotion",
        "data": emotion_detail
    }

    topic = f"student/{student_uid}/eegemotion"
    _publish_msgpack(
        topic=topic,
        payload_dict=emotion_data,
        success_text=f"EEG情绪结果发送成功：student_id={student_uid}, pred={emotionlist[index]}, topic={topic}"
    )