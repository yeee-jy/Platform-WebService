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
TOPIC = f"student/{STUDENT_ID}/rppg"
QOS = 0

# =========================
# rPPG 协议配置（按新的结构）
# =========================
DATA_TYPE = "rppg"
SOURCE = "rppg_service"
SAMPLING_RATE = 30
SEND_INTERVAL_SECONDS = 1.0


def generate_rppg_segment(
    student_id: str,
    sampling_rate: int = 30,
    heart_rate_bpm: float = 72.4,
    spo2: float = 98.1,
    source: str = "rppg_service",
    base_timestamp_ms: int | None = None,
) -> Dict[str, Any]:
    """
    模拟生成 1 秒 rPPG 数据包（按新协议）
    仅包含：
    - heart_waveform
    - heart_rate
    - spo2
    """

    if base_timestamp_ms is None:
        base_timestamp_ms = int(time.time() * 1000)

    n = sampling_rate
    start_timestamp = base_timestamp_ms
    end_timestamp = base_timestamp_ms + 1000

    heart_freq = heart_rate_bpm / 60.0
    heart_waveform: List[float] = []

    for i in range(n):
        t = i / sampling_rate

        # 模拟 rPPG 心率波形：主频 + 谐波 + 少量噪声
        heart_val = (
            0.12 * math.sin(2 * math.pi * heart_freq * t)
            + 0.04 * math.sin(2 * math.pi * 2 * heart_freq * t + 0.5)
            + 0.01 * math.sin(2 * math.pi * 3 * heart_freq * t - 0.4)
            + 0.005 * random.gauss(0, 1)
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
            "spo2": round(spo2, 1),
        },
    }
    return payload


def serialize_rppg_msgpack(payload: Dict[str, Any]) -> bytes:
    return msgpack.packb(payload, use_bin_type=True)


def deserialize_rppg_msgpack(body: bytes) -> Dict[str, Any]:
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
        "spo2",
    }
    missing = expected_inner_keys - set(data.keys())
    if missing:
        raise ValueError(f"missing data keys: {missing}")

    if obj["data_type"] != "rppg":
        raise ValueError(f"unexpected data_type: {obj['data_type']}")

    if not isinstance(data["heart_waveform"], list):
        raise ValueError("heart_waveform is not list")

    fs = int(data["sampling_rate"])
    if len(data["heart_waveform"]) != fs:
        raise ValueError("heart_waveform length != sampling_rate")

    return obj


def create_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(client_id="rppg_publisher_demo_student1", clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    return client


def publish_once(client: mqtt.Client, student_id: str, segment_start_ms: int) -> int:
    """
    发布 1 个 1 秒包，并返回下一包建议起始时间。
    """
    hr = 72.4 + random.uniform(-2.0, 2.0)
    spo2 = 98.1 + random.uniform(-0.8, 0.8)

    payload = generate_rppg_segment(
        student_id=student_id,
        sampling_rate=SAMPLING_RATE,
        heart_rate_bpm=hr,
        spo2=spo2,
        source=SOURCE,
        base_timestamp_ms=segment_start_ms,
    )

    body = serialize_rppg_msgpack(payload)
    decoded = deserialize_rppg_msgpack(body)

    result = client.publish(
        topic=f"student/{student_id}/rppg",
        payload=body,
        qos=QOS,
        retain=False,
    )
    result.wait_for_publish()

    print("=" * 60)
    print("published topic:", f"student/{student_id}/rppg")
    print("payload bytes:", len(body))
    print("student_id:", decoded["student_id"])
    print("data_type:", decoded["data_type"])
    print("timestamp:", decoded["data"]["timestamp"])
    print("source:", decoded["data"]["source"])
    print("sampling_rate:", decoded["data"]["sampling_rate"])
    print("start_timestamp:", decoded["data"]["start_timestamp"])
    print("end_timestamp:", decoded["data"]["end_timestamp"])
    print("heart_rate:", decoded["data"]["heart_rate"])
    print("spo2:", decoded["data"]["spo2"])
    print("heart_waveform len:", len(decoded["data"]["heart_waveform"]))
    print("heart_waveform first 5:", decoded["data"]["heart_waveform"][:5])

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
        print("student style: rPPG heart waveform + spo2")
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