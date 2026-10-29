#工具函数
from datetime import datetime, timedelta
from LinkPostgreSQL import batch_insert_to_db
import numpy as np
# import LSTMtest
from collections import deque
import time
from wristbandUseModel import load_ppg_emotion_model, infer_ppg_emotion
from rabbitmq_utils_to_Teacher import send_ppgemotion_result

# 全局变量：存储滑动窗口大小
_sliding_window_seconds = 10

# 设置滑动窗口
def set_sliding_window(sliding_size):
    """
    设置滑动窗口大小
    :param sliding_size: int/float，滑动窗口时长（单位：秒），必须大于0
    :return: bool，设置成功返回True，失败返回False
    """
    global _sliding_window_seconds
    if isinstance(sliding_size, (int, float)) and sliding_size > 0:
        _sliding_window_seconds = sliding_size
        print(f"滑动窗口大小已设置为：{sliding_size} 秒")
        return True
    else:
        print(f"无效的窗口大小！必须是大于0的数字（当前输入：{sliding_size}）")
        return False

def get_sliding_window():
    """
    获取当前的滑动窗口大小
    :return: int/float，当前窗口时长（秒）
    """
    global _sliding_window_seconds
    return _sliding_window_seconds

# 全局变量：数据缓冲区，用来存放还未形成完整窗口的EEG数据
_data_buffer = []

completed_window_data = []
_window_count = 0  # 滑动窗口计数器

def extract_data(data):
    """
    从EEG数据中提取特征（channelData）和标签（trigger）
    :param data: EEG数据对象列表，每个对象包含channelData和trigger
    :return: 特征矩阵和标签数组
    """
    features = [entry.channelData for entry in data]  # 提取每条数据的channelData作为特征
    labels = [entry.trigger for entry in data]       # 提取每条数据的trigger作为标签
    return np.array(features), np.array(labels)

# def add_data(new_data,conn,metadata_id):
#     """
#     将新接收到的EEG数据添加到缓冲区，并检查是否能形成完整的窗口。
#     如果能，就会打印出这个窗口的信息
#     :param new_data: 一个EEGSensorData对象
#     """
#     global _data_buffer, _sliding_window_seconds,_window_count
#     # 将整数时间戳转换为 datetime 对象
#     try:
#         timestamp = new_data.timestamp
#
#         # 检查 timestamp 是否为整数
#         if isinstance(timestamp, int):
#             datetime_obj = datetime.fromtimestamp(timestamp / 1000.0)
#             new_data.timestamp = datetime_obj
#             print(f"[Utils] 整数时间戳 {timestamp} 已成功转换为: {datetime_obj}")
#         else:
#             datetime_obj = datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M:%S.%f")
#             new_data.timestamp = datetime_obj
#             print(f"[Utils] 字符串时间戳 {timestamp} 已成功转换为: {datetime_obj}")
#
#     except Exception as e:
#         print(f"[Utils] 时间格式转换失败: {e}")
#         return
#
#     LSTMtest.try_predict_on_new_data(new_data)
#     # 把新来的数据放进缓冲区
#     _data_buffer.append(new_data)
#     print(f"[ADD] 收到新数据，时间: {new_data.timestamp}。缓冲区现在有 {len(_data_buffer)} 条数据。")
#
#     # 检查缓冲区里的数据是否足够组成一个完整的窗口
#     # 我们需要至少两条数据来判断时间跨度
#     if len(_data_buffer) < 2:
#         print("[LESS] 缓冲区数据不足，等待更多数据...")
#         return
#
#     # 计算窗口的时间范围
#     # 窗口的起始时间就是缓冲区里最早一条数据的时间
#     window_start_time = _data_buffer[0].timestamp
#     # 窗口的结束时间 = 起始时间 + 窗口大小
#     window_end_time = window_start_time + timedelta(seconds=_sliding_window_seconds)
#
#     print(f"[SCOPE] 当前窗口时间范围: {window_start_time} ~ {window_end_time}")
#
#     # 判断是否有足够的数据进行存储
#     # 如果缓冲区里最后一条数据的时间也超过了窗口结束时间，说明缓冲区里的数据已经包含了至少一个完整的窗口
#     if _data_buffer[-1].timestamp > window_end_time:
#         print("[SUCCESS] 发现一个完整的窗口！")
#
#         # 提取这个完整窗口内的所有数据
#         for data in _data_buffer:
#             if data.timestamp <= window_end_time:
#                 completed_window_data.append(data)
#             else:
#                 break
#
#         _window_count += 1
#         # 处理这个完整的窗口
#         print(f"[INCLUDE] 完整窗口包含 {len(completed_window_data)} 条数据。")
#
#         # 打印一下窗口的起始和结束时间
#         print(f"[Utils] 窗口内容: 从 {completed_window_data[0].timestamp} 到 {completed_window_data[-1].timestamp}")
#
#         # 计算DE特征
#         # DE = compute_entropy(completed_window_data)
#         # print(f"[DE] DE特征: {DE}")
#
#
#
#         # 原始数据存入数据库
#         insert_success = batch_insert_to_db(
#             conn=conn,
#             metadata_id=metadata_id,
#             window_data=completed_window_data
#         )
#         if not insert_success:
#             print(f"[WINDOW WARNING] 窗口 {_window_count} 数据插入失败，请检查数据库连接或数据格式")
#
#
#         # 清理缓冲区：将已经处理过的数据从缓冲区中移除，剩下的数据将作为下一个窗口的起始部分
#         _data_buffer = _data_buffer[len(completed_window_data):]
#         print(f"[Utils] 处理完毕，缓冲区剩余 {len(_data_buffer)} 条数据，等待新数据...")
#     else:
#         print("[Utils] 缓冲区数据尚未填满一个窗口，继续等待...")
#
#     print(f"[ALL_DATA] 目前一共存储的滑动窗口的数量：{_window_count}\n")

# 全局变量：加载模型（只需要初始化一次）
net_lrcn, net_att, net_fc = load_ppg_emotion_model(
    lrcn_path="./models/PPG_models/PPG/models/ALL_25_1/best_model_lrcn.pth",
    att_path="./models/PPG_models/PPG/models/ALL_25_1/best_model_att.pth",
    fc_path="./models/PPG_models/PPG/models/ALL_25_1/best_model_fc.pth"
)

########################### 下面是 PPG 数据的操作代码 #############################

import time
from collections import deque
import numpy as np

# ========= 全局配置 =========
TARGET_FS = 64             # 模型要求 64Hz
WINDOW_DURATION = 25       # 25 秒
STEP_DURATION = 1          # 1 秒步长
LEFT_BUFFER_MS = 1000.0    # 插值时保留窗口左侧 1s 缓冲
FALLBACK_RAW_FS = 45.0     # time_intervals 不可靠时的保底原始频率
STALE_STATE_SECONDS = 120  # 超过 120s 没有新数据就清理该学生状态


# 每个学生单独维护一份状态
# {
#   "10001": {
#       "ppg_queue": deque([(ts_ms, value), ...]),
#       "last_trigger_data_ts": float | None,
#       "last_seen_wall_time": float
#   },
#   ...
# }
student_ppg_states = {}


def _get_student_state(student_id: str):
    student_id = str(student_id)
    if student_id not in student_ppg_states:
        student_ppg_states[student_id] = {
            "ppg_queue": deque(),
            "last_trigger_data_ts": None,
            "last_seen_wall_time": time.time(),
        }
    return student_ppg_states[student_id]


def _cleanup_stale_student_states():
    """清理长时间不再上报数据的学生状态，避免状态无限增长。"""
    now = time.time()
    stale_ids = []

    for sid, state in student_ppg_states.items():
        last_seen = state.get("last_seen_wall_time", 0)
        if now - last_seen > STALE_STATE_SECONDS:
            stale_ids.append(sid)

    for sid in stale_ids:
        try:
            del student_ppg_states[sid]
            print(f"[PPG][{sid}] 状态已清理（超过 {STALE_STATE_SECONDS}s 无新数据）")
        except KeyError:
            pass


def _reconstruct_point_timestamps(packet_ts, n, time_intervals):
    """
    根据 packet.timestamp + time_intervals 还原包内每个点的时间戳。
    默认 packet_ts 表示“这一包最后一个点”的时间戳（ms）。
    返回长度为 n 的 point_ts 列表。
    """
    point_ts = [0.0] * n

    if n <= 0:
        return point_ts

    # 优先用 time_intervals
    # 允许：
    # 1) len(time_intervals) == n-1   -> 正好是相邻点间隔
    # 2) len(time_intervals) >= n     -> 取前 n-1 个
    if len(time_intervals) >= n - 1 and n > 1:
        try:
            dts_ms = [float(x) * 1000.0 for x in time_intervals[: n - 1]]

            # 从最后一个点倒推
            point_ts[-1] = float(packet_ts)
            for i in range(n - 2, -1, -1):
                point_ts[i] = point_ts[i + 1] - dts_ms[i]

            # 简单校验：时间应单调递增
            monotonic = True
            for i in range(1, n):
                if point_ts[i] <= point_ts[i - 1]:
                    monotonic = False
                    break

            if monotonic:
                return point_ts

        except Exception as e:
            print(f"[PPG] time_intervals 还原失败，改用 fallback 频率: {e}")

    # fallback：time_intervals 不够或异常时，按约 45Hz 近似
    approx_dt_ms = 1000.0 / FALLBACK_RAW_FS
    start_ts = float(packet_ts) - (n - 1) * approx_dt_ms
    for i in range(n):
        point_ts[i] = start_ts + i * approx_dt_ms

    return point_ts


def _emit_ppg_emotion_result(student_id, pred_class, pred_name):
    """
    统一封装发送结果。
    这里优先尝试较完整的调用方式；如果你项目里的 send_ppgemotion_result
    只有旧签名，会自动 fallback。
    """
    student_id = str(student_id)
    timestamp = int(time.time() * 1000)

    # 1) 优先尝试关键词参数
    try:
        return send_ppgemotion_result(
            student_id=student_id,
            pred_class=int(pred_class),
            pred_name=str(pred_name),
            data_type="wristbandemotion",
            source="ppg_emotion_recognizer",
            summary=True,
            timestamp=timestamp,
        )
    except TypeError:
        pass
    except Exception as e:
        print(f"[PPG][{student_id}] 关键词发送失败: {e}")

    # 2) 尝试三参数：student_id, pred_class, pred_name
    try:
        return send_ppgemotion_result(student_id, int(pred_class), str(pred_name))
    except TypeError:
        pass
    except Exception as e:
        print(f"[PPG][{student_id}] 三参数发送失败: {e}")

    # 3) 尝试三参数：pred_class, pred_name, student_id
    try:
        return send_ppgemotion_result(int(pred_class), str(pred_name), student_id)
    except TypeError:
        pass
    except Exception as e:
        print(f"[PPG][{student_id}] 三参数(另一顺序)发送失败: {e}")

    # 4) 尝试旧版两参数：pred_name, student_id
    try:
        return send_ppgemotion_result(str(pred_name), student_id)
    except Exception as e:
        print(f"[PPG][{student_id}] 发送结果失败，请检查 send_ppgemotion_result 的函数签名: {e}")
        return None


def add_ppg_data(data):
    """
    data 结构：
    {
        "student_id": "10001",
        "data_type": "wristband",
        "timestamp": 1774356030412,      # 默认视为“这一包最后一个点”的时间戳(ms)
        "ppg_filtered": [...],           # 一包的 PPG 滤波值
        "time_intervals": [...],         # 相邻点间隔（秒）
    }
    """
    student_id = data.get("student_id")
    packet_ts = data.get("timestamp")
    ppg_filtered = data.get("ppg_filtered", [])
    time_intervals = data.get("time_intervals", [])
    if not student_id:
        print(f"[PPG] 数据格式错误，缺少 student_id, data={data}")
        return

    student_id = str(student_id)

    if packet_ts is None or not ppg_filtered:
        print(f"[PPG][{student_id}] 数据格式错误，缺少 timestamp 或 ppg_filtered, data={data}")
        return

    n = len(ppg_filtered)
    if n == 0:
        return

    # 获取该学生独立状态
    state = _get_student_state(student_id)
    state["last_seen_wall_time"] = time.time()

    ppg_queue = state["ppg_queue"]
    last_trigger_data_ts = state["last_trigger_data_ts"]

    # ---------- 1) 还原包内逐点时间 ----------
    point_ts = _reconstruct_point_timestamps(packet_ts, n, time_intervals)

    # ---------- 2) 逐点入队（只进入当前学生自己的队列） ----------
    for ts, val in zip(point_ts, ppg_filtered):
        try:
            ppg_queue.append((float(ts), float(val)))
        except Exception:
            continue

    if not ppg_queue:
        return

    # ---------- 3) 先判断是否满窗，再裁剪 ----------
    latest_ts = ppg_queue[-1][0]
    window_start_ts = latest_ts - WINDOW_DURATION * 1000.0

    oldest_ts = ppg_queue[0][0]
    current_coverage_ms = latest_ts - oldest_ts
    current_coverage_s = current_coverage_ms / 1000.0
    missing_s = max(0.0, WINDOW_DURATION - current_coverage_s)

    # 历史还没覆盖到窗口起点，不触发
    if oldest_ts > window_start_ts:
        print(
            f"[PPG][{student_id}] 窗口未满: 当前已覆盖 {current_coverage_s:.3f}s / "
            f"{WINDOW_DURATION}s, 还差 {missing_s:.3f}s"
        )
        return

    # 满窗后再裁剪，但保留左边 1s 缓冲，方便插值
    trim_before_ts = window_start_ts - LEFT_BUFFER_MS
    while len(ppg_queue) > 1 and ppg_queue[1][0] < trim_before_ts:
        ppg_queue.popleft()

    # ---------- 4) 控制 1 秒步长（每个学生独立控制） ----------
    if last_trigger_data_ts is not None:
        if latest_ts - last_trigger_data_ts < STEP_DURATION * 1000.0:
            return

    # ---------- 5) 取最近窗口数据 ----------
    window_points = [(ts, v) for ts, v in ppg_queue if ts >= trim_before_ts]

    if len(window_points) < 2:
        return

    window_ts = np.array([ts for ts, _ in window_points], dtype=np.float64)
    window_vals = np.array([v for _, v in window_points], dtype=np.float64)

    # 去重，防止重复时间戳导致插值异常
    unique_ts, unique_indices = np.unique(window_ts, return_index=True)
    unique_vals = window_vals[unique_indices]

    if len(unique_ts) < 2:
        return

    # ---------- 6) 重采样到 64Hz ----------
    target_count = TARGET_FS * WINDOW_DURATION   # 64 * 25 = 1600
    target_ts = np.linspace(
        window_start_ts,
        window_start_ts + WINDOW_DURATION * 1000.0,
        target_count,
        endpoint=False,
        dtype=np.float64
    )

    model_input = np.interp(target_ts, unique_ts, unique_vals).astype(np.float32)

    print(
        f"\n[PPG][{student_id}] 触发模型：窗口={WINDOW_DURATION}s, "
        f"原始点数={len(window_vals)}, 重采样后点数={len(model_input)}"
    )

    # ---------- 7) 模型推理 ----------
    pred_class, pred_name = infer_ppg_emotion(
        net_lrcn, net_att, net_fc, model_input.tolist()
    )
    print(f"[PPG][{student_id}] 当前PPG窗口预测情绪：{pred_name}（类别：{pred_class}）")

    # ---------- 8) 发送结果 ----------
    _emit_ppg_emotion_result(student_id, pred_class, pred_name)

    # ---------- 9) 更新该学生状态 ----------
    state["last_trigger_data_ts"] = latest_ts

    # ---------- 10) 顺手清理过期学生 ----------
    _cleanup_stale_student_states()