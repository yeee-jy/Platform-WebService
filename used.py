import msgpack
import paho.mqtt.client as mqtt

# 配置和发布者一致
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
STUDENT_UID = "10001"
MQTT_USERNAME = "admin"
MQTT_PASSWORD = "ccnu@1290"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("订阅者连接成功，开始订阅主题...")
        client.subscribe(f"student/{STUDENT_UID}/wristbandemotion", qos=1)
    else:
        print(f"订阅者连接失败，错误码：{rc}")

def on_message(client, userdata, msg):
    print(f"\n收到消息（主题：{msg.topic}）：")
    # 反序列化msgpack数据
    data = msgpack.unpackb(msg.payload, raw=False)
    print(f"原始数据：{data}")
    print(f"情绪名称：{data['data']['pred_name']}")
    print(f"时间戳：{data['data']['timestamp']}")

# 初始化订阅者客户端
client = mqtt.Client(protocol=mqtt.MQTTv311)
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_forever()