import asyncio
import json
import msgpack
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Set, Union
from datetime import datetime
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from fastapi import WebSocket
from pydantic import BaseModel, field_validator

from app.modules.rabbitmq import RabbitMQ

# 解包函数
from datastream_bridge import (
    deserialize_bcg_msgpack,
    deserialize_mmwave_msgpack,
    deserialize_rppg_msgpack,
    deserialize_wristband_msgpack,
)

SUMMARY_STUDENT_ID = "__summary__"

DataType = Literal[
    "eeg",
    "wristband",
    "emotion",
    "cognition",
    "wristbandemotion",
    "eegemotion",
    "bcg",
    "mmwave",
    "rppg",
    "all",
]

ALL_DATA_TYPES: Set[DataType] = {
    "eeg",
    "wristband",
    "emotion",
    "cognition",
    "wristbandemotion",
    "eegemotion",
    "bcg",
    "mmwave",
    "rppg",
}

# 当前支持的“汇总字段提取器”
SUMMARY_EXTRACTORS = {
    "mmwave": lambda payload: {
        "summary": True,
        "student_id": payload["student_id"],
        "data_type": payload["data_type"],

        "timestamp": payload.get("timestamp"),
        "source": payload.get("source"),
        "sampling_rate": payload.get("sampling_rate"),
        "start_timestamp": payload.get("start_timestamp"),
        "end_timestamp": payload.get("end_timestamp"),

        "heart_rate": payload.get("heart_rate"),
        "respiratory_rate": payload.get("respiratory_rate"),
        "fatigue_state": payload.get("fatigue_state"),

        "ibi_30s_ms": payload.get("ibi_30s_ms", []),
        "ibi_valid_count": payload.get("ibi_valid_count", 0),
        "ibi_bin_count": payload.get("ibi_bin_count"),
        "ibi_bin_size_ms": payload.get("ibi_bin_size_ms"),
        "ibi_window_start_timestamp": payload.get("ibi_window_start_timestamp"),
        "ibi_window_end_timestamp": payload.get("ibi_window_end_timestamp"),
        "is_human_present": payload.get("is_human_present", False),
    },

    "rppg": lambda payload: {
        "summary": True,
        "student_id": payload["student_id"],
    },

    "wristbandemotion": lambda payload: {
        "summary": True,
        "student_id": payload["student_id"],
        "pred_class": payload["pred_class"],
        "pred_name": payload["pred_name"],
        "timestamp": payload["timestamp"],
        "source": payload["source"],
    },
    "bcg": lambda payload: {
        "summary": True,
        "student_id": payload["student_id"],
        "sbp": payload["sbp"],
        "dbp": payload["dbp"],
    },
}


async def publish_ppg_infer_task(infer_payload: dict):
    """
    将 wristband 推理所需数据投递到独立推理队列 ppg_infer
    """
    try:
        body = msgpack.packb(infer_payload, use_bin_type=True)

        async with RabbitMQ.get_channel(prefetch_count=10) as channel:
            await RabbitMQ.declare_queue(channel, "ppg_infer", durable=True)

            message = aio_pika.Message(
                body=body,
                content_type="application/msgpack",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )

            await channel.default_exchange.publish(
                message,
                routing_key="ppg_infer",
            )

    except Exception as e:
        print(f"[PPG-INFER] 投递推理队列失败: {e}")


class SubscribeKey(BaseModel):
    subscriptions: Dict[str, Set[DataType]]

    @field_validator("subscriptions", mode="before")
    @classmethod
    def validate_subscriptions(cls, v):
        if not isinstance(v, dict):
            raise TypeError("subscriptions must be a dict")

        normalized: Dict[str, Set[DataType]] = {}
        valid_types = set(ALL_DATA_TYPES) | {"all"}

        for stu_id, types in v.items():
            if isinstance(types, str):
                type_set = {types}
            elif isinstance(types, (list, set, tuple)):
                type_set = set(types)
            else:
                raise TypeError(f"Invalid subscription value for {stu_id}: {types}")

            for t in type_set:
                if t not in valid_types:
                    raise ValueError(f"Invalid data type: {t}")

            if "all" in type_set:
                normalized[stu_id] = set(ALL_DATA_TYPES)
            else:
                normalized[stu_id] = type_set

        return normalized

    def match(self, *, student_id: str, data_type: str) -> bool:
        types = self.subscriptions.get(student_id)
        return types is not None and data_type in types

    def add(self, student_id: str, types: Set[DataType]):
        self.subscriptions.setdefault(student_id, set()).update(types)

    def remove(self, student_id: str, types: Set[DataType]):
        if student_id not in self.subscriptions:
            return
        self.subscriptions[student_id] -= types
        if not self.subscriptions[student_id]:
            del self.subscriptions[student_id]


class SubscribeRequest(SubscribeKey):
    msg_type: Literal["subscribe", "subscribe_add", "subscribe_remove"]


@dataclass(slots=True)
class _WSConn:
    """
    封装单个 WebSocket 连接，避免直接以 WebSocket 作为 dict value
    """
    ws: WebSocket
    key: Optional[SubscribeKey] = None


class WebsocketManager:
    """
    应用级 WebSocket 管理器（并发安全）
    - 生命周期由 FastAPI app.state 管理
    - 支持 RabbitMQ 回调并发 publish
    """

    def __init__(self):
        self._connections: Dict[int, _WSConn] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections[id(ws)] = _WSConn(ws=ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.pop(id(ws), None)

    async def send_text(self, message: str, ws: WebSocket):
        try:
            await ws.send_text(message)
        except Exception:
            await self.disconnect(ws)

    async def send_bytes(self, data: bytes, ws: WebSocket):
        try:
            await ws.send_bytes(data)
        except Exception:
            await self.disconnect(ws)

    async def send_json(self, data, ws: WebSocket, *, mode="text"):
        try:
            await ws.send_json(data, mode=mode)
        except Exception:
            await self.disconnect(ws)

    async def broadcast_text(self, message: str):
        async with self._lock:
            conns = list(self._connections.values())

        coros = [self.send_text(message, conn.ws) for conn in conns]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def broadcast_bytes(self, data: bytes):
        async with self._lock:
            conns = list(self._connections.values())

        coros = [self.send_bytes(data, conn.ws) for conn in conns]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def broadcast_json(self, data, *, mode="text"):
        async with self._lock:
            conns = list(self._connections.values())

        coros = [self.send_json(data, conn.ws, mode=mode) for conn in conns]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def handle_subscribe(self, ws: WebSocket, req: SubscribeRequest):
        print("收到订阅:", req)

        async with self._lock:
            conn = self._connections.get(id(ws))
            if conn is None:
                return

            if conn.key is None:
                conn.key = SubscribeKey(subscriptions={})

            key = conn.key

            if req.msg_type == "subscribe":
                key.subscriptions = req.subscriptions

            elif req.msg_type == "subscribe_add":
                for sid, types in req.subscriptions.items():
                    key.add(sid, types)

            elif req.msg_type == "subscribe_remove":
                for sid, types in req.subscriptions.items():
                    key.remove(sid, types)

    async def has_summary_subscription(self, data_type: str) -> bool:
        """
        检查当前是否存在 __summary__ + 指定 data_type 的订阅
        """
        async with self._lock:
            conns = list(self._connections.values())

        for conn in conns:
            key = conn.key
            if key is None:
                continue
            if key.match(student_id=SUMMARY_STUDENT_ID, data_type=data_type):
                return True
        return False

    def _build_summary_payload(self, *, data_type: str, payload: dict) -> Optional[dict]:
        extractor = SUMMARY_EXTRACTORS.get(data_type)
        if extractor is None:
            return None
        try:
            return extractor(payload)
        except Exception as e:
            print(f"构造 summary payload 失败, data_type={data_type}, err={e}")
            return None

    async def publish(self, *, student_id: str, data_type: str, payload: Union[bytes, dict]):
        """
        统一发布逻辑：
        - 如果某连接订阅的是 __summary__ + data_type：只发送提取后的 summary 数据
        - 如果某连接订阅的是 student_id + data_type：只发送该学生完整数据
        """
        async with self._lock:
            conns = list(self._connections.values())

        coros = []
        summary_payload = None
        summary_payload_ready = False

        for conn in conns:
            key = conn.key
            if key is None:
                continue

            # 1) 订阅的是汇总
            if key.match(student_id=SUMMARY_STUDENT_ID, data_type=data_type):
                if not isinstance(payload, dict):
                    continue

                if not summary_payload_ready:
                    summary_payload = self._build_summary_payload(
                        data_type=data_type,
                        payload=payload,
                    )
                    summary_payload_ready = True

                if summary_payload is not None:
                    coros.append(self.send_json(summary_payload, conn.ws))

                continue

            # 2) 订阅的是单个学生
            if key.match(student_id=student_id, data_type=data_type):
                if data_type == "eeg":
                    coros.append(self.send_bytes(payload, conn.ws))
                else:
                    coros.append(self.send_json(payload, conn.ws))

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def on_rabbitmq_msg(self, message: AbstractIncomingMessage):
        async with message.process():
            routing_key = message.routing_key
            try:
                _, student_id, data_type = routing_key.split(".")
            except ValueError:
                return

            # -------------------------------------------------
            # wristband：解包 + 按需投递推理队列
            # 只有当前存在 __summary__ + wristbandemotion 订阅时，才触发 PPG 推理
            # -------------------------------------------------
            if data_type == "wristband":
                try:
                    packet = deserialize_wristband_msgpack(message.body)

                    # 给前端展示的完整数据
                    payload = {
                        "student_id": packet.student_id,
                        "data_type": packet.data_type,
                        "timestamp": packet.timestamp,

                        # 心率
                        "heart_rate": packet.heart_rate,

                        # 手环采样率，固定 50Hz
                        "sampling_rate": packet.sampling_rate,

                        # PPG / 脉搏波数据
                        "raw_calib_data": packet.raw_calib_data,
                        "ppg_raw": packet.ppg_raw,
                        "ppg_filtered": packet.ppg_filtered,

                        # GSR / 皮肤电
                        "gsr": packet.gsr,
                        "skin_resistance": packet.skin_resistance,

                        # 加速度数据
                        "sensor_data": packet.sensor_data,
                        "accel_x": packet.accel_x,
                        "accel_y": packet.accel_y,
                        "accel_z": packet.accel_z,
                    }

                    time_intervals = [1.0 / packet.sampling_rate] * len(packet.ppg_filtered)

                    infer_payload = {
                        "student_id": packet.student_id,
                        "data_type": "wristband",
                        "timestamp": packet.timestamp,

                        "heart_rate": packet.heart_rate,
                        "sampling_rate": packet.sampling_rate,

                        "ppg_filtered": packet.ppg_filtered,

                        # 如果旧推理服务需要这个字段，就临时生成
                        "time_intervals": time_intervals,

                        "gsr": packet.gsr,
                        "skin_resistance": packet.skin_resistance,

                        "accel_x": packet.accel_x,
                        "accel_y": packet.accel_y,
                        "accel_z": packet.accel_z,
                    }
                    need_ppg_infer = await self.has_summary_subscription("wristbandemotion")
                    # print(packet.gsr)
                    if need_ppg_infer:
                        asyncio.create_task(publish_ppg_infer_task(infer_payload))
                        # print(f"[PPG-INFER-PUB] 已投递推理任务, student_id={real_student_id}")

                except Exception as e:
                    print("wristband 解包失败:", e)
                    print(message.body[:200])
                    return

            elif data_type == "bcg":
                try:
                    packet = deserialize_bcg_msgpack(message.body)
                    payload = {
                        "student_id": packet.student_id,
                        "data_type": packet.data_type,
                        "timestamp": packet.timestamp,
                        "source": packet.source,
                        "sampling_rate": packet.sampling_rate,
                        "start_timestamp": packet.start_timestamp,
                        "end_timestamp": packet.end_timestamp,
                        "heart_waveform": packet.heart_waveform,
                        "heart_rate": packet.heart_rate,
                        "sbp": packet.sbp,
                        "dbp": packet.dbp,
                    }
                    student_id = packet.student_id
                except Exception as e:
                    print("BCG 解包失败:", e)
                    print(message.body[:200])
                    return

            elif data_type == "mmwave":
                try:
                    packet = deserialize_mmwave_msgpack(message.body)
                    payload = {
                        "student_id": packet.student_id,
                        "data_type": packet.data_type,
                        "timestamp": packet.timestamp,
                        "source": packet.source,
                        "sampling_rate": packet.sampling_rate,
                        "start_timestamp": packet.start_timestamp,
                        "end_timestamp": packet.end_timestamp,
                        "heart_wave_filtered": packet.heart_wave_filtered,
                        "breath_wave_filtered": packet.breath_wave_filtered,
                        "ibi_30s_ms": packet.ibi_30s_ms,
                        "ibi_valid_count": packet.ibi_valid_count,
                        "ibi_bin_count": packet.ibi_bin_count,
                        "ibi_bin_size_ms": packet.ibi_bin_size_ms,
                        "ibi_window_start_timestamp": packet.ibi_window_start_timestamp,
                        "ibi_window_end_timestamp": packet.ibi_window_end_timestamp,
                        "heart_rate": packet.heart_rate,
                        "respiratory_rate": packet.respiratory_rate,
                        "fatigue_state": "非疲劳",
                        "is_human_present": packet.is_human_present,
                    }
                    # print(packet.fatigue_state)
                    # print(packet.occupancy)
                    # print(packet.heart_wave_filtered)
                    # print(packet.breath_wave_filtered)
                    student_id = packet.student_id
                except Exception as e:
                    print("mmwave 解包失败:", e)
                    print(message.body[:200])
                    return

            elif data_type == "rppg":
                try:
                    packet = deserialize_rppg_msgpack(message.body)
                    payload = {
                        "student_id": packet.student_id,
                        "data_type": packet.data_type,
                        "timestamp": packet.timestamp,
                        "source": packet.source,
                        "sampling_rate": packet.sampling_rate,
                        "start_timestamp": packet.start_timestamp,
                        "end_timestamp": packet.end_timestamp,
                        "heart_waveform": packet.heart_waveform,
                        "heart_rate": packet.heart_rate,
                        "spo2": packet.spo2,
                    }
                    student_id = packet.student_id
                except Exception as e:
                    print("rPPG 解包失败:", e)
                    print(message.body[:200])
                    return

            elif data_type == "wristbandemotion":
                try:
                    packet = msgpack.unpackb(message.body, raw=False)

                    detail = packet.get("data", {})
                    payload = {
                        "student_id": str(packet.get("student_id", student_id)),
                        "data_type": packet.get("data_type", "wristbandemotion"),
                        "pred_class": detail.get("pred_class"),
                        "pred_name": detail.get("pred_name"),
                        "timestamp": detail.get("timestamp"),
                        "source": detail.get("source"),
                    }

                    student_id = payload["student_id"]

                except Exception as e:
                    print("wristbandemotion 解包失败:", e)
                    print(message.body[:200])
                    return

            elif data_type == "eegemotion":
                try:
                    packet = msgpack.unpackb(message.body, raw=False)

                    detail = packet.get("data", {})
                    payload = {
                        "student_id": str(packet.get("student_id", student_id)),
                        "data_type": packet.get("data_type", "eegemotion"),
                        "pred_class": detail.get("pred_class"),
                        "pred_name": detail.get("pred_name"),
                        "timestamp": detail.get("timestamp"),
                        "source": detail.get("source"),
                    }

                    student_id = payload["student_id"]

                except Exception as e:
                    print("eegemotion 解包失败:", e)
                    print(message.body[:200])
                    return

            else:
                return

            await self.publish(
                student_id=student_id,
                data_type=data_type,
                payload=payload,
            )


async def data_consumer_task(mgr: WebsocketManager):
    """
    从 RabbitMQ 队列中消费学生的生理信号数据
    """
    async with RabbitMQ.get_channel(prefetch_count=10) as channel:
        exchange = await RabbitMQ.get_exchange(channel, "amq.topic")
        queue = await RabbitMQ.declare_queue(channel, "datastream_ws", auto_delete=True)

        # 绑定所有学生的所有数据
        await queue.bind(exchange, routing_key="student.*.*")

        await queue.consume(mgr.on_rabbitmq_msg)

        print("[RabbitMQ] Connected and consuming...")

        try:
            await asyncio.Future()
        finally:
            await channel.close()