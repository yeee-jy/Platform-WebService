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

STUDENT_ID = "10002"
TOPIC = f"student/{STUDENT_ID}/bcg"
QOS = 0

# =========================
# BCG 协议配置
# =========================
DATA_TYPE = "bcg"
SOURCE = "bcg_service_student2"
SAMPLING_RATE = 125
SEND_INTERVAL_SECONDS = 1.0


def generate_bcg_segment(
    student_id: str,
    sampling_rate: int = 125,
    heart_rate_bpm: float = 96.0,        # 学生2：明显更快
    respiratory_rate_bpm: float = 10.0,  # 学生2：明显更慢
    source: str = "bcg_service_student2",
    base_timestamp_ms: int | None = None,
) -> Dict[str, Any]:
    """
    模拟生成 1 秒 BCG 数据包（学生2专属风格）
    特点：
    - 心率更快
    - 呼吸更慢
    - 心搏波更尖更高
    - 呼吸波更大且略微上移
    """

    if base_timestamp_ms is None:
        base_timestamp_ms = int(time.time() * 1000)

    n = sampling_rate
    dt_ms = int(round(1000.0 / sampling_rate))

    start_timestamp = base_timestamp_ms
    end_timestamp = base_timestamp_ms + (n - 1) * dt_ms

    heart_freq = heart_rate_bpm / 60.0
    resp_freq = respiratory_rate_bpm / 60.0

    heart_waveform: List[float] = []
    resp_waveform: List[float] = []

    for i in range(n):
        t = i / sampling_rate

        heart_phase = 2 * math.pi * heart_freq * t
        resp_phase = 2 * math.pi * resp_freq * t

        # 学生2：心搏波做得更“尖”
        # 多谐波叠加，让曲线更像明显的搏动，而不是圆滑正弦
        heart_val = (
            1.35 * math.sin(heart_phase)
            + 0.55 * math.sin(2 * heart_phase + 0.25)
            + 0.22 * math.sin(3 * heart_phase - 0.4)
            + 0.08 * math.sin(4 * heart_phase + 1.1)
            + 0.03 * random.gauss(0, 1)
        )

        # 学生2：呼吸波更慢、更大，并带一点上移偏置
        resp_val = (
            1.8 * math.sin(resp_phase + 0.4)
            + 0.25 * math.sin(2 * resp_phase - 0.6)
            + 0.12   # 整体上移一点，前端更容易认
            + 0.02 * random.gauss(0, 1)
        )

        heart_waveform.append(round(heart_val, 6))
        resp_waveform.append(round(resp_val, 6))

    payload = {
        "student_id": student_id,
        "data_type": DATA_TYPE,
        "data": {
            "timestamp": int(time.time() * 1000),
            "source": source,
            "sampling_rate": sampling_rate,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "heart_waveform": heart_waveform,
            "resp_waveform": resp_waveform,
            "heart_rate": round(heart_rate_bpm, 2),
            "respiratory_rate": round(respiratory_rate_bpm, 2),
        },
    }
    return payload


def serialize_bcg_msgpack(payload: Dict[str, Any]) -> bytes:
    return msgpack.packb(payload, use_bin_type=True)


def deserialize_bcg_msgpack(body: bytes) -> Dict[str, Any]:
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
        "resp_waveform",
        "heart_rate",
        "respiratory_rate",
    }
    missing = expected_inner_keys - set(data.keys())
    if missing:
        raise ValueError(f"missing data keys: {missing}")

    if obj["data_type"] != "bcg":
        raise ValueError(f"unexpected data_type: {obj['data_type']}")

    fs = int(data["sampling_rate"])
    if len(data["heart_waveform"]) != fs:
        raise ValueError("heart_waveform length != sampling_rate")
    if len(data["resp_waveform"]) != fs:
        raise ValueError("resp_waveform length != sampling_rate")

    return obj


def create_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(client_id="bcg_publisher_demo_student2", clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    return client


def publish_once(client: mqtt.Client, student_id: str, segment_start_ms: int) -> int:
    """
    发布 1 个 1 秒包，并返回下一包建议起始时间。
    学生2保持比较稳定的“个性化特征”。
    """
    hr = 96.0 + random.uniform(-1.5, 1.5)
    rr = 10.0 + random.uniform(-0.4, 0.4)

    payload = generate_bcg_segment(
        student_id=student_id,
        sampling_rate=SAMPLING_RATE,
        heart_rate_bpm=hr,
        respiratory_rate_bpm=rr,
        source=SOURCE,
        base_timestamp_ms=segment_start_ms,
    )

    body = serialize_bcg_msgpack(payload)
    decoded = deserialize_bcg_msgpack(body)

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
    print("source:", decoded["data"]["source"])
    print("sampling_rate:", decoded["data"]["sampling_rate"])
    print("start_timestamp:", decoded["data"]["start_timestamp"])
    print("end_timestamp:", decoded["data"]["end_timestamp"])
    print("heart_rate:", decoded["data"]["heart_rate"])
    print("respiratory_rate:", decoded["data"]["respiratory_rate"])
    print("heart_waveform len:", len(decoded["data"]["heart_waveform"]))
    print("resp_waveform len:", len(decoded["data"]["resp_waveform"]))

    dt_ms = int(round(1000.0 / SAMPLING_RATE))
    next_start_ms = decoded["data"]["end_timestamp"] + dt_ms
    return next_start_ms


def main():
    client = create_mqtt_client()
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    try:
        current_start_ms = int(time.time() * 1000)

        print("MQTT connected.")
        print("topic:", TOPIC)
        print("student style: FAST HEART + SLOW RESP")
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