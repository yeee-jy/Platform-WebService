# ppg_model_infer.py
import torch
import numpy as np
import librosa
import sys
import os

# 获取当前脚本所在目录并构造目标路径
current_file_path = os.path.abspath(__file__)
root_dir = os.path.dirname(current_file_path)
ppg_dir = os.path.join(root_dir, "models", "PPG_models", "PPG")

# 添加到系统路径以便导入 utils
sys.path.append(ppg_dir)

# 确保 utils.py 存在于 ppg_dir 目录下后再执行导入
try:
    from utils import Net_LRCN, Net_Attention, Net_FC
except ImportError as e:
    raise ImportError(f"无法从 {ppg_dir} 中导入 utils，请检查 utils.py 是否存在且包含所需类: {e}")

# -------------------------- 模型配置 --------------------------
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
MODEL_INPUT_SIZE = 1600    # 模型要求的输入点数（25s×64Hz）
WIN_LEN = 64               # STFT窗口长度
OVERLAP = 16               # STFT重叠步长
CUT_OFF_FREQ = 8           # 截止频率（Hz）
# 情绪标签映射
EMOTION_LABELS = {
    0: "困惑",
    1: "中性",
    2: "无聊",
    3: "专注"
}


def load_ppg_emotion_model(
    lrcn_path="./models/ALL_25_1/best_model_lrcn.pth",
    att_path="./models/ALL_25_1/best_model_att.pth",
    fc_path="./models/ALL_25_1/best_model_fc.pth"
):
    """
    加载PPG情绪识别模型
    :param lrcn_path: Net_LRCN权重路径
    :param att_path: Net_Attention权重路径
    :param fc_path: Net_FC权重路径
    :return: 加载好的三个模型（net_lrcn, net_att, net_fc）
    """
    # 初始化模型
    net_lrcn = Net_LRCN().to(DEVICE)
    net_att = Net_Attention().to(DEVICE)
    net_fc = Net_FC(4).to(DEVICE)

    # 加载权重
    net_lrcn.load_state_dict(torch.load(lrcn_path, map_location=DEVICE))
    net_att.load_state_dict(torch.load(att_path, map_location=DEVICE))
    net_fc.load_state_dict(torch.load(fc_path, map_location=DEVICE))

    # 设置为评估模式
    net_lrcn.eval()
    net_att.eval()
    net_fc.eval()

    return net_lrcn, net_att, net_fc


def preprocess_ppg_data(window_data):
    """
    预处理PPG窗口数据，转换成模型需要的输入格式
    :param window_data: 一维列表/数组，实时PPG窗口数据
    :return: 模型需要的两个输入张量（X_input, ATT_input）
    """
    # 将窗口数据调整为模型要求的1600个点（插值/截断）,利用两边的值和的一半进行填充
    window_data = np.array(window_data, dtype=np.float32)
    if len(window_data) != MODEL_INPUT_SIZE:
        window_data = np.interp(
            np.linspace(0, len(window_data)-1, MODEL_INPUT_SIZE),
            np.arange(len(window_data)),
            window_data
        )

    # 计算STFT，生成频谱图
    x_stft = librosa.stft(window_data, n_fft=WIN_LEN, hop_length=OVERLAP, win_length=WIN_LEN)
    magnitude = np.abs(x_stft)
    log_spectrogram = librosa.amplitude_to_db(magnitude)

    # 转换成模型需要的张量格式：[batch, channel, freq, time]
    X_input = torch.tensor(log_spectrogram[np.newaxis, np.newaxis, :CUT_OFF_FREQ + 1, :]).float().to(DEVICE)
    ATT_input = torch.tensor(log_spectrogram[np.newaxis, np.newaxis, :, :]).float().to(DEVICE)

    return X_input, ATT_input


def infer_ppg_emotion(net_lrcn, net_att, net_fc, window_data):
    """
    调用模型进行PPG情绪识别
    :param net_lrcn: 加载好的Net_LRCN模型
    :param net_att: 加载好的Net_Attention模型
    :param net_fc: 加载好的Net_FC模型
    :param window_data: 你的实时PPG窗口数据（一维列表）
    :return: 预测的情绪类别（int）、情绪名称（str）
    """
    # 预处理数据
    X_input, ATT_input = preprocess_ppg_data(window_data)

    # 模型推理（无梯度模式，加速推理）
    with torch.no_grad():
        feat = net_lrcn(X_input)
        attention = net_att(ATT_input)
        output = net_fc(feat, attention)

    # 获取预测结果
    pred_class = torch.argmax(output, dim=1).item()
    pred_name = EMOTION_LABELS.get(pred_class, "未知情绪")

    return pred_class, pred_name