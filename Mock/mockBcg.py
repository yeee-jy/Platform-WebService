import math
import random
import time
from typing import Dict, Any, List

import msgpack
import paho.mqtt.client as mqtt


# =========================
# MQTT 配置
# =========================
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
USERNAME = "admin"
PASSWORD = "ccnu@1290"

STUDENT_ID = "10001"
TOPIC = f"student/{STUDENT_ID}/bcg"
QOS = 0

# =========================
# BCG 协议配置（按你新的结构）
# =========================
DATA_TYPE = "bcg"
SOURCE = "bcg_service"
SAMPLING_RATE = 30           # 新示例里是 30
SEND_INTERVAL_SECONDS = 1.0  # 每秒发送 1 包


def generate_bcg_segment(
    student_id: str,
    sampling_rate: int = 30,
    heart_rate_bpm: float = 72.0,
    sbp: float = 118.0,
    dbp: float = 76.0,
    source: str = "bcg_service",
    base_timestamp_ms: int | None = None,
) -> Dict[str, Any]:
    """
    模拟生成 1 秒 BCG 数据包（按新协议）
    - 仅保留 heart_waveform / heart_rate / sbp / dbp
    - 不再包含 resp_waveform / respiratory_rate
    """

    if base_timestamp_ms is None:
        base_timestamp_ms = int(time.time() * 1000)

    n = sampling_rate
    dt_ms = int(round(1000.0 / sampling_rate))

    start_timestamp = base_timestamp_ms
    end_timestamp = base_timestamp_ms + 1000  # 按你的示例风格，更像整秒结束时间

    # bpm -> Hz
    heart_freq = heart_rate_bpm / 60.0

    heart_waveform: List[float] = []

    for i in range(n):
        t = i / sampling_rate

        # 模拟心搏波形：主频 + 二次谐波 + 少量噪声
        heart_val = (
            0.9 * math.sin(2 * math.pi * heart_freq * t)
            + 0.25 * math.sin(2 * math.pi * 2 * heart_freq * t + 0.5)
            + 0.05 * random.gauss(0, 1)
        )

        heart_waveform.append(round(heart_val, 6))

    payload = {
        "student_id": student_id,
        "data_type": DATA_TYPE,
        "data": {
            "timestamp": end_timestamp,
            "source": source,
            "sampling_rate": sampling_rate,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "heart_waveform": heart_waveform,
            "heart_rate": round(heart_rate_bpm, 1),
            "sbp": round(sbp, 1),
            "dbp": round(dbp, 1),
        },
    }
    return payload


def serialize_bcg_msgpack(payload: Dict[str, Any]) -> bytes:
    """
    按约定使用 msgpack 序列化为二进制。
    """
    return msgpack.packb(payload, use_bin_type=True)


def deserialize_bcg_msgpack(body: bytes) -> Dict[str, Any]:
    """
    本地校验用：反序列化检查格式是否正确。
    """
    obj = msgpack.unpackb(body, raw=False)

    if not isinstance(obj, dict):
        raise ValueError(f"payload is not dict, got {type(obj)!r}")

    for key in ("student_id", "data_type", "data"):
        if key not in obj:
            raise ValueError(f"missing top-level key: {key}")

    data = obj["data"]
    if not isinstance(data, dict):
        raise ValueError("payload['data'] is not dict")

    expected_inner_keys = {
        "timestamp",
        "source",
        "sampling_rate",
        "start_timestamp",
        "end_timestamp",
        "heart_waveform",
        "heart_rate",
        "sbp",
        "dbp",
    }
    missing = expected_inner_keys - set(data.keys())
    if missing:
        raise ValueError(f"missing data keys: {missing}")

    if obj["data_type"] != "bcg":
        raise ValueError(f"unexpected data_type: {obj['data_type']}")

    fs = int(data["sampling_rate"])
    if len(data["heart_waveform"]) != fs:
        raise ValueError("heart_waveform length != sampling_rate")

    return obj


def create_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(client_id="bcg_publisher_demo", clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    return client


def publish_once(client: mqtt.Client, student_id: str, segment_start_ms: int) -> int:
    """
    发布 1 个 1 秒包，并返回下一包建议起始时间。
    """
    # 做一点轻微抖动，更像真实数据
    hr = 72.3 + random.uniform(-2.0, 2.0)
    sbp = 118.6 + random.uniform(-3.0, 3.0)
    dbp = 76.4 + random.uniform(-2.0, 2.0)

    payload = generate_bcg_segment(
        student_id=student_id,
        sampling_rate=SAMPLING_RATE,
        heart_rate_bpm=hr,
        sbp=sbp,
        dbp=dbp,
        source=SOURCE,
        base_timestamp_ms=segment_start_ms,
    )

    body = serialize_bcg_msgpack(payload)

    # 本地反序列化校验
    decoded = deserialize_bcg_msgpack(body)

    # 发送
    result = client.publish(
        topic=f"student/{student_id}/bcg",
        payload=body,
        qos=QOS,
        retain=False,
    )
    result.wait_for_publish()

    print("=" * 60)
    print("published topic:", f"student/{student_id}/bcg")
    print("payload bytes:", len(body))
    print("student_id:", decoded["student_id"])
    print("data_type:", decoded["data_type"])
    print("timestamp:", decoded["data"]["timestamp"])
    print("sampling_rate:", decoded["data"]["sampling_rate"])
    print("start_timestamp:", decoded["data"]["start_timestamp"])
    print("end_timestamp:", decoded["data"]["end_timestamp"])
    print("heart_rate:", decoded["data"]["heart_rate"])
    print("sbp:", decoded["data"]["sbp"])
    print("dbp:", decoded["data"]["dbp"])
    print("heart_waveform len:", len(decoded["data"]["heart_waveform"]))

    # 下一包从上一包结束时间继续
    next_start_ms = decoded["data"]["end_timestamp"]
    return next_start_ms


def main():
    client = create_mqtt_client()
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    try:
        current_start_ms = int(time.time() * 1000)

        print("MQTT connected.")
        print("topic:", TOPIC)
        print("press Ctrl+C to stop")

        while True:
            t0 = time.time()
            current_start_ms = publish_once(
                client=client,
                student_id=STUDENT_ID,
                segment_start_ms=current_start_ms,
            )

            elapsed = time.time() - t0
            sleep_time = max(0.0, SEND_INTERVAL_SECONDS - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("stopped by user")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()