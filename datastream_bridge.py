#############################################################解包BCG的代码################################
import msgpack
from dataclasses import dataclass
from typing import List, Optional, Any, Dict

@dataclass
class BcgPayload:
    student_id: str
    data_type: str
    timestamp: int
    source: str
    sampling_rate: int
    start_timestamp: int
    end_timestamp: int
    heart_waveform: List[float]
    heart_rate: float
    sbp: float
    dbp: float


def deserialize_bcg_msgpack(body: bytes) -> BcgPayload:
    """
    适用于当前 BCG 发送端的 msgpack 解包。
    """
    obj = msgpack.unpackb(body, raw=False)

    data = obj["data"]

    return BcgPayload(
        student_id=obj["student_id"],
        data_type=obj["data_type"],
        timestamp=data["timestamp"],
        source=data["source"],
        sampling_rate=data["sampling_rate"],
        start_timestamp=data["start_timestamp"],
        end_timestamp=data["end_timestamp"],
        heart_waveform=[float(x) for x in data["heart_waveform"]],
        heart_rate=float(data["heart_rate"]),
        sbp=float(data["sbp"]),
        dbp=float(data["dbp"]),
    )
#############################################################################################

#########################################mmWAV解包代码############################################
import msgpack
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MmwavePayload:
    student_id: str
    data_type: str

    timestamp: int
    source: str
    sampling_rate: int
    start_timestamp: int
    end_timestamp: int

    heart_wave_filtered: List[float]
    breath_wave_filtered: List[float]
    ibi_30s_ms: List[float]

    ibi_valid_count: Optional[int]
    ibi_bin_count: Optional[int]
    ibi_bin_size_ms: Optional[int]
    ibi_window_start_timestamp: Optional[int]
    ibi_window_end_timestamp: Optional[int]

    heart_rate: Optional[float]
    respiratory_rate: Optional[float]
    fatigue_state: Optional[str]
    is_human_present: Optional[bool]


def _to_optional_float(value):
    if value is None:
        return None
    return float(value)


def _to_optional_int(value):
    if value is None:
        return None
    return int(value)


def _to_optional_bool(value):
    if value is None:
        return None
    return bool(value)


def _to_optional_str(value):
    if value is None:
        return None
    return str(value)


def _to_float_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"期望 list，实际是 {type(value)}")
    return [float(x) for x in value]


def deserialize_mmwave_msgpack(body: bytes) -> MmwavePayload:
    """
    适用于新版 mmwave 发送端的 msgpack 解包。
    协议结构：
    {
        "student_id": "...",
        "data_type": "mmwave",
        "data": {
            "timestamp": ...,
            "source": "mmwave_service",
            "sampling_rate": ...,
            "start_timestamp": ...,
            "end_timestamp": ...,
            "heart_wave_filtered": [...],
            "breath_wave_filtered": [...],
            "ibi_30s_ms": [...],
            "ibi_valid_count": ...,
            "ibi_bin_count": ...,
            "ibi_bin_size_ms": ...,
            "ibi_window_start_timestamp": ...,
            "ibi_window_end_timestamp": ...,
            "heart_rate": ...,
            "respiratory_rate": ...,
            "fatigue_state": ...,
            "is_human_present": ...
        }
    }
    """
    obj = msgpack.unpackb(body, raw=False)

    if not isinstance(obj, dict):
        raise TypeError("msgpack 解包结果不是 dict")

    data = obj.get("data")
    if not isinstance(data, dict):
        raise TypeError("payload 中 data 字段不是 dict")

    return MmwavePayload(
        student_id=str(obj["student_id"]),
        data_type=str(obj["data_type"]),

        timestamp=int(data["timestamp"]),
        source=str(data["source"]),
        sampling_rate=int(data["sampling_rate"]),
        start_timestamp=int(data["start_timestamp"]),
        end_timestamp=int(data["end_timestamp"]),

        heart_wave_filtered=_to_float_list(data.get("heart_wave_filtered")),
        breath_wave_filtered=_to_float_list(data.get("breath_wave_filtered")),
        ibi_30s_ms=_to_float_list(data.get("ibi_30s_ms")),

        ibi_valid_count=_to_optional_int(data.get("ibi_valid_count")),
        ibi_bin_count=_to_optional_int(data.get("ibi_bin_count")),
        ibi_bin_size_ms=_to_optional_int(data.get("ibi_bin_size_ms")),
        ibi_window_start_timestamp=_to_optional_int(data.get("ibi_window_start_timestamp")),
        ibi_window_end_timestamp=_to_optional_int(data.get("ibi_window_end_timestamp")),

        heart_rate=_to_optional_float(data.get("heart_rate")),
        respiratory_rate=_to_optional_float(data.get("respiratory_rate")),
        fatigue_state=_to_optional_str(data.get("fatigue_state")),
        is_human_present=_to_optional_bool(data.get("is_human_present")),
    )
#############################################################################################

######################################### rPPG 解包代码 ############################################
import msgpack
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RppgPayload:
    student_id: str
    data_type: str
    timestamp: int
    source: str
    sampling_rate: int
    start_timestamp: int
    end_timestamp: int
    heart_waveform: List[float]
    heart_rate: Optional[float]
    spo2: Optional[float]


def _to_optional_float(value):
    if value is None:
        return None
    return float(value)


def deserialize_rppg_msgpack(body: bytes) -> RppgPayload:
    """
    适用于当前新版 rPPG 发送端的 msgpack 解包。
    协议结构：
    {
        "student_id": "...",
        "data_type": "rppg",
        "data": {
            "timestamp": ...,
            "source": "rppg_service",
            "sampling_rate": ...,
            "start_timestamp": ...,
            "end_timestamp": ...,
            "heart_waveform": [...],
            "heart_rate": ...,
            "spo2": ...
        }
    }
    """
    obj = msgpack.unpackb(body, raw=False)

    if not isinstance(obj, dict):
        raise TypeError("msgpack 解包结果不是 dict")

    if obj.get("data_type") != "rppg":
        raise ValueError(f"unexpected data_type: {obj.get('data_type')}")

    data = obj.get("data")
    if not isinstance(data, dict):
        raise TypeError("payload 中 data 字段不是 dict")

    return RppgPayload(
        student_id=str(obj["student_id"]),
        data_type=str(obj["data_type"]),
        timestamp=int(data["timestamp"]),
        source=str(data["source"]),
        sampling_rate=int(data["sampling_rate"]),
        start_timestamp=int(data["start_timestamp"]),
        end_timestamp=int(data["end_timestamp"]),
        heart_waveform=[float(x) for x in data.get("heart_waveform", [])],
        heart_rate=_to_optional_float(data.get("heart_rate")),
        spo2=_to_optional_float(data.get("spo2")),
    )
#############################################################################################

################################## 手环数据解析 ###########################################

from dataclasses import dataclass
from typing import List
import msgpack


@dataclass(slots=True)
class WristbandPayload:
    student_id: str
    data_type: str

    timestamp: int

    # data[1] 是心率/ppg值，不是采样率
    heart_rate: float

    # 手环采样率固定 50Hz
    sampling_rate: float

    # PPG / 脉搏波数据
    raw_calib_data: List[List[float]]
    ppg_raw: List[float]
    ppg_filtered: List[float]

    # GSR / 皮肤电
    gsr: List[float]
    skin_resistance: List[float]

    # 加速度数据
    sensor_data: List[List[float]]
    accel_x: List[float]
    accel_y: List[float]
    accel_z: List[float]


def deserialize_wristband_msgpack(body: bytes) -> WristbandPayload:
    """
    当前 wristband msgpack 解包。

    根据 C++ WristbandPacket::fromJsonObject 对应关系：

    data[0] -> timestamp
    data[1] -> heart_rate / ppg
    data[2] -> pulseWaveDatas -> [[rawVal, filtedVal], ...]
    data[3] -> gsrs -> [gsr, gsr, ...]
    data[4] -> accDatas -> [[x, y, z], ...]
    """

    obj = msgpack.unpackb(body, raw=False)

    if not isinstance(obj, dict):
        raise TypeError("msgpack 解包结果不是 dict")

    if obj.get("data_type") != "wristband":
        raise ValueError(f"unexpected data_type: {obj.get('data_type')}")

    data = obj.get("data")
    if not isinstance(data, (list, tuple)):
        raise TypeError("payload 中 data 字段不是 list/tuple")

    if len(data) < 5:
        raise ValueError(f"wristband data 长度不足，当前长度: {len(data)}")

    # ===============================
    # 基础信息
    # ===============================

    timestamp = int(data[0])

    # 注意：data[1] 是心率/ppg，不是 sampling_rate
    heart_rate = float(data[1])

    # 手环固定 50Hz
    sampling_rate = 50.0

    # ===============================
    # 原始字段
    # ===============================

    raw_calib_data_src = data[2] if isinstance(data[2], (list, tuple)) else []

    # 关键修改：data[3] 是 GSR，不是 time_intervals
    gsr_src = data[3] if isinstance(data[3], (list, tuple)) else []

    sensor_data_src = data[4] if isinstance(data[4], (list, tuple)) else []

    # ===============================
    # 解析 PPG / 脉搏波
    # ===============================

    raw_calib_data: List[List[float]] = []
    ppg_raw: List[float] = []
    ppg_filtered: List[float] = []

    for item in raw_calib_data_src:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue

        try:
            raw_val = float(item[0])
            filt_val = float(item[1])
        except Exception:
            continue

        raw_calib_data.append([raw_val, filt_val])
        ppg_raw.append(raw_val)
        ppg_filtered.append(filt_val)

    # ===============================
    # 解析 GSR / 皮肤电
    # ===============================

    gsr: List[float] = []

    for item in gsr_src:
        try:
            gsr.append(float(item))
        except Exception:
            continue

    # ===============================
    # 解析加速度
    # ===============================

    sensor_data: List[List[float]] = []
    accel_x: List[float] = []
    accel_y: List[float] = []
    accel_z: List[float] = []

    for item in sensor_data_src:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue

        try:
            ax = float(item[0])
            ay = float(item[1])
            az = float(item[2])
        except Exception:
            continue

        sensor_data.append([ax, ay, az])
        accel_x.append(ax)
        accel_y.append(ay)
        accel_z.append(az)

    return WristbandPayload(
        student_id=str(obj.get("student_id", "unknown")),
        data_type=str(obj.get("data_type", "wristband")),

        timestamp=timestamp,

        heart_rate=heart_rate,
        sampling_rate=sampling_rate,

        raw_calib_data=raw_calib_data,
        ppg_raw=ppg_raw,
        ppg_filtered=ppg_filtered,

        gsr=gsr,
        skin_resistance=gsr,

        sensor_data=sensor_data,
        accel_x=accel_x,
        accel_y=accel_y,
        accel_z=accel_z,
    )

#############################################################################################
