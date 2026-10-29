import math
import random
import time
from typing import Dict, Any, List, Tuple

import msgpack
import paho.mqtt.client as mqtt


# =========================
# MQTT 配置
# =========================
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
USERNAME = "admin"
PASSWORD = "ccnu@1290"

# 改这里即可切换学生
STUDENT_ID = "10001"
TOPIC = f"student/{STUDENT_ID}/mmwave"
QOS = 0

# =========================
# mmwave 协议配置
# =========================
DATA_TYPE = "mmwave"
SOURCE = "mmwave_service"
SAMPLING_RATE = 20
SEND_INTERVAL_SECONDS = 1.0

# 文档要求：ibi_30s_ms 固定为最近 30 秒、30 个 1 秒 bin
IBI_WINDOW_SECONDS = 30
IBI_BIN_COUNT = 30
IBI_BIN_SIZE_MS = 1000

# mock 行为配置
# True: 一直有人，避免前端出现“没人没数据”
# False: 按 PRESENCE_SWITCH_SECONDS 周期切换有人/无人
FORCE_HUMAN_PRESENT = True
PRESENCE_SWITCH_SECONDS = 10

# 有人时轮流切换疲劳状态
FATIGUE_STATES = ["清醒", "疲劳", "初始化中", "未知"]


def build_ibi_snapshot_and_valid_count(
    heart_rate_bpm: float,
    is_human_present: bool,
) -> Tuple[List[float], int]:
    """
    生成符合文档语义的 IBI 快照。

    返回：
    - ibi_30s_ms: 长度固定为 30，每个元素对应一个 1 秒 bin
    - ibi_valid_count: 当前窗口内完整有效 IBI 数量，不要求等于 30，也不要求等于数组长度

    文档要求：
    - ibi_30s_ms 长度固定为 30
    - 无人时为 30 个 0.0
    - ibi_valid_count 是有效 IBI 数，不等于数组长度
    """
    if not is_human_present or heart_rate_bpm <= 0:
        return [0.0] * IBI_BIN_COUNT, 0

    target_ibi = 60000.0 / heart_rate_bpm

    # 模拟完整有效 IBI 数量：30 秒窗口内心搏间期数量通常约等于 30 * HR / 60
    # 这里让它和文档语义一致：它是“有效 IBI 数量”，而不是 30 个 bin 的长度
    base_valid_count = int(round(IBI_WINDOW_SECONDS * heart_rate_bpm / 60.0))
    valid_count = max(8, base_valid_count + random.randint(-2, 2))

    ibi_bins: List[float] = []
    prev_val = target_ibi + random.uniform(-10.0, 10.0)

    for _ in range(IBI_BIN_COUNT):
        # 做得更像“每秒一个 bin 的代表值”，数值连续一些
        drift = random.uniform(-12.0, 12.0)
        val = 0.75 * prev_val + 0.25 * (target_ibi + drift)
        val = max(500.0, min(1400.0, val))
        ibi_bins.append(round(val, 1))
        prev_val = val

    return ibi_bins, valid_count


def generate_mmwave_segment(
    student_id: str,
    sampling_rate: int = 20,
    heart_rate_bpm: float = 78.0,
    respiratory_rate_bpm: float = 16.0,
    fatigue_state: str = "清醒",
    is_human_present: bool = True,
    source: str = "mmwave_service",
    base_timestamp_ms: int | None = None,
) -> Dict[str, Any]:
    """
    模拟生成 1 秒 mmwave 数据包。
    """
    if base_timestamp_ms is None:
        base_timestamp_ms = int(time.time() * 1000)

    n = sampling_rate
    dt_ms = int(round(1000.0 / sampling_rate))

    start_timestamp = base_timestamp_ms
    end_timestamp = base_timestamp_ms + (n - 1) * dt_ms

    ibi_window_end_timestamp = end_timestamp
    ibi_window_start_timestamp = ibi_window_end_timestamp - IBI_WINDOW_SECONDS * 1000 + 1

    if not is_human_present:
        heart_wave_filtered = [0.0] * n
        breath_wave_filtered = [0.0] * n
        ibi_30s_ms = [0.0] * IBI_BIN_COUNT
        ibi_valid_count = 0

        return {
            "student_id": student_id,
            "data_type": DATA_TYPE,
            "data": {
                "timestamp": end_timestamp,
                "source": source,
                "sampling_rate": sampling_rate,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "heart_wave_filtered": heart_wave_filtered,
                "breath_wave_filtered": breath_wave_filtered,
                "ibi_30s_ms": ibi_30s_ms,
                "ibi_valid_count": ibi_valid_count,
                "ibi_bin_count": IBI_BIN_COUNT,
                "ibi_bin_size_ms": IBI_BIN_SIZE_MS,
                "ibi_window_start_timestamp": ibi_window_start_timestamp,
                "ibi_window_end_timestamp": ibi_window_end_timestamp,
                "heart_rate": 0.0,
                "respiratory_rate": 0.0,
                "fatigue_state": "无人",
                "is_human_present": False,
            },
        }

    heart_freq = heart_rate_bpm / 60.0
    resp_freq = respiratory_rate_bpm / 60.0

    heart_wave_filtered: List[float] = []
    breath_wave_filtered: List[float] = []

    heart_amp = 0.020 + random.uniform(-0.003, 0.003)
    breath_amp = 0.045 + random.uniform(-0.006, 0.006)

    for i in range(n):
        t = i / sampling_rate

        heart_phase = 2 * math.pi * heart_freq * t
        resp_phase = 2 * math.pi * resp_freq * t

        heart_val = (
            heart_amp * math.sin(heart_phase)
            + 0.35 * heart_amp * math.sin(2 * heart_phase + 0.4)
            + 0.12 * heart_amp * math.sin(3 * heart_phase - 0.3)
            + 0.0015 * random.gauss(0, 1)
        )

        breath_val = (
            breath_amp * math.sin(resp_phase + 0.6)
            + 0.18 * breath_amp * math.sin(2 * resp_phase - 0.5)
            + 0.0010 * random.gauss(0, 1)
        )

        heart_wave_filtered.append(round(heart_val, 6))
        breath_wave_filtered.append(round(breath_val, 6))

    ibi_30s_ms, ibi_valid_count = build_ibi_snapshot_and_valid_count(
        heart_rate_bpm=heart_rate_bpm,
        is_human_present=True,
    )

    return {
        "student_id": student_id,
        "data_type": DATA_TYPE,
        "data": {
            "timestamp": end_timestamp,
            "source": source,
            "sampling_rate": sampling_rate,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "heart_wave_filtered": heart_wave_filtered,
            "breath_wave_filtered": breath_wave_filtered,
            "ibi_30s_ms": ibi_30s_ms,
            "ibi_valid_count": ibi_valid_count,
            "ibi_bin_count": IBI_BIN_COUNT,
            "ibi_bin_size_ms": IBI_BIN_SIZE_MS,
            "ibi_window_start_timestamp": ibi_window_start_timestamp,
            "ibi_window_end_timestamp": ibi_window_end_timestamp,
            "heart_rate": round(heart_rate_bpm, 2),
            "respiratory_rate": round(respiratory_rate_bpm, 2),
            "fatigue_state": fatigue_state,
            "is_human_present": True,
        },
    }


def serialize_mmwave_msgpack(payload: Dict[str, Any]) -> bytes:
    return msgpack.packb(payload, use_bin_type=True)


def deserialize_mmwave_msgpack(body: bytes) -> Dict[str, Any]:
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
        "heart_wave_filtered",
        "breath_wave_filtered",
        "ibi_30s_ms",
        "ibi_valid_count",
        "ibi_bin_count",
        "ibi_bin_size_ms",
        "ibi_window_start_timestamp",
        "ibi_window_end_timestamp",
        "heart_rate",
        "respiratory_rate",
        "fatigue_state",
        "is_human_present",
    }
    missing = expected_inner_keys - set(data.keys())
    if missing:
        raise ValueError(f"missing data keys: {missing}")

    if obj["data_type"] != DATA_TYPE:
        raise ValueError(f"unexpected data_type: {obj['data_type']}")

    fs = int(data["sampling_rate"])
    if len(data["heart_wave_filtered"]) != fs:
        raise ValueError("heart_wave_filtered length != sampling_rate")
    if len(data["breath_wave_filtered"]) != fs:
        raise ValueError("breath_wave_filtered length != sampling_rate")

    if not isinstance(data["ibi_30s_ms"], list):
        raise ValueError("ibi_30s_ms is not list")

    # 文档要求：ibi_30s_ms 长度固定为 30
    if len(data["ibi_30s_ms"]) != IBI_BIN_COUNT:
        raise ValueError(f"ibi_30s_ms length must be {IBI_BIN_COUNT}")

    if int(data["ibi_bin_count"]) != IBI_BIN_COUNT:
        raise ValueError(f"ibi_bin_count must be {IBI_BIN_COUNT}")

    if int(data["ibi_bin_size_ms"]) != IBI_BIN_SIZE_MS:
        raise ValueError(f"ibi_bin_size_ms must be {IBI_BIN_SIZE_MS}")

    # 注意：这里不再校验 ibi_valid_count == len(ibi_30s_ms)
    # 因为文档语义里，这两个本来就不是一回事。

    return obj


def create_mqtt_client() -> mqtt.Client:
    # 让 client_id 跟 student_id 绑定，复制第二个学生时不容易撞
    client = mqtt.Client(
        client_id=f"mmwave_publisher_demo_{STUDENT_ID}",
        clean_session=True,
    )
    client.username_pw_set(USERNAME, PASSWORD)
    return client


def is_human_present_by_seq(seq: int) -> bool:
    if FORCE_HUMAN_PRESENT:
        return True

    packets_per_block = max(1, int(PRESENCE_SWITCH_SECONDS / SEND_INTERVAL_SECONDS))
    block_index = seq // packets_per_block
    return block_index % 2 == 0


def publish_once(client: mqtt.Client, student_id: str, segment_start_ms: int, seq: int) -> int:
    human_present = is_human_present_by_seq(seq)

    if human_present:
        fatigue_state = FATIGUE_STATES[seq % len(FATIGUE_STATES)]

        if fatigue_state == "清醒":
            hr = 78.0 + random.uniform(-2.0, 2.0)
            rr = 16.0 + random.uniform(-0.8, 0.8)
        elif fatigue_state == "疲劳":
            hr = 72.0 + random.uniform(-2.0, 2.0)
            rr = 14.0 + random.uniform(-0.8, 0.8)
        elif fatigue_state == "初始化中":
            hr = 75.0 + random.uniform(-2.0, 2.0)
            rr = 15.0 + random.uniform(-0.8, 0.8)
        else:
            hr = 76.0 + random.uniform(-2.0, 2.0)
            rr = 15.0 + random.uniform(-0.8, 0.8)
    else:
        fatigue_state = "无人"
        hr = 0.0
        rr = 0.0

    payload = generate_mmwave_segment(
        student_id=student_id,
        sampling_rate=SAMPLING_RATE,
        heart_rate_bpm=hr,
        respiratory_rate_bpm=rr,
        fatigue_state=fatigue_state,
        is_human_present=human_present,
        source=SOURCE,
        base_timestamp_ms=segment_start_ms,
    )

    body = serialize_mmwave_msgpack(payload)
    decoded = deserialize_mmwave_msgpack(body)

    result = client.publish(
        topic=TOPIC,
        payload=body,
        qos=QOS,
        retain=False,
    )
    result.wait_for_publish()

    print("=" * 60)
    print("published topic:", TOPIC)
    print("seq:", seq)
    print("payload bytes:", len(body))
    print("student_id:", decoded["student_id"])
    print("data_type:", decoded["data_type"])
    print("source:", decoded["data"]["source"])
    print("sampling_rate:", decoded["data"]["sampling_rate"])
    print("start_timestamp:", decoded["data"]["start_timestamp"])
    print("end_timestamp:", decoded["data"]["end_timestamp"])
    print("heart_rate:", decoded["data"]["heart_rate"])
    print("respiratory_rate:", decoded["data"]["respiratory_rate"])
    print("fatigue_state:", decoded["data"]["fatigue_state"])
    print("is_human_present:", decoded["data"]["is_human_present"])
    print("ibi_valid_count:", decoded["data"]["ibi_valid_count"])
    print("ibi_bin_count:", decoded["data"]["ibi_bin_count"])
    print("ibi_bin_size_ms:", decoded["data"]["ibi_bin_size_ms"])
    print("ibi_window_start_timestamp:", decoded["data"]["ibi_window_start_timestamp"])
    print("ibi_window_end_timestamp:", decoded["data"]["ibi_window_end_timestamp"])
    print("heart_wave_filtered len:", len(decoded["data"]["heart_wave_filtered"]))
    print("breath_wave_filtered len:", len(decoded["data"]["breath_wave_filtered"]))
    print("ibi_30s_ms len:", len(decoded["data"]["ibi_30s_ms"]))
    print("heart_wave_filtered first 5:", decoded["data"]["heart_wave_filtered"][:5])
    print("breath_wave_filtered first 5:", decoded["data"]["breath_wave_filtered"][:5])
    print("ibi_30s_ms first 5:", decoded["data"]["ibi_30s_ms"][:5])

    dt_ms = int(round(1000.0 / SAMPLING_RATE))
    next_start_ms = decoded["data"]["end_timestamp"] + dt_ms
    return next_start_ms


def main():
    client = create_mqtt_client()
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    try:
        current_start_ms = int(time.time() * 1000)
        seq = 0

        print("MQTT connected.")
        print("topic:", TOPIC)
        print("student_id:", STUDENT_ID)
        print("mode:", "always human present" if FORCE_HUMAN_PRESENT else "toggle presence")
        print("student style: mmwave heart + breath filtered wave + fixed 30-bin ibi snapshot")
        print("press Ctrl+C to stop")

        while True:
            t0 = time.time()
            current_start_ms = publish_once(
                client=client,
                student_id=STUDENT_ID,
                segment_start_ms=current_start_ms,
                seq=seq,
            )
            seq += 1

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