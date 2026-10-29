

import torch
from utils import Net_LRCN, Net_Attention, Net_FC

# 设置设备
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# 加载模型
net_lrcn = Net_LRCN().to(DEVICE)
net_att = Net_Attention().to(DEVICE)
net_fc = Net_FC(4).to(DEVICE)  # 假设类别数量为4

# 加载权重
net_lrcn.load_state_dict(torch.load('./models/ALL_25_1/best_model_lrcn.pth', map_location=DEVICE))
net_att.load_state_dict(torch.load('./models/ALL_25_1/best_model_att.pth', map_location=DEVICE))
net_fc.load_state_dict(torch.load('./models/ALL_25_1/best_model_fc.pth', map_location=DEVICE))

# # 加载权重
# net_lrcn.load_state_dict(torch.load('./models/teacher/S8_net_lrcn_yes.pt', map_location=DEVICE))
# net_att.load_state_dict(torch.load('./models/teacher/S8_net_att_yes.pt', map_location=DEVICE))
# net_fc.load_state_dict(torch.load('./models/teacher/S8_net_fc_yes.pt', map_location=DEVICE))



# 设置模型为评估模式
net_lrcn.eval()
net_att.eval()
net_fc.eval()

import numpy as np
import librosa
import pandas as pd


def preprocess_real_time_data(real_time_data):
    # 假设 real_time_data 是一个一维的时间序列数据
    WIN_LEN = 64  # 窗口长度
    OVERLAP = 16
    CUT_OFF_FREQ = 8  # HZ

    # 计算STFT
    x_stft = librosa.stft(real_time_data, n_fft=WIN_LEN, hop_length=OVERLAP, win_length=WIN_LEN)
    magnitude = np.abs(x_stft)
    log_spectrogram = librosa.amplitude_to_db(magnitude)

    # 转换成模型输入的格式
    X_input = torch.tensor(log_spectrogram[np.newaxis, np.newaxis, :CUT_OFF_FREQ + 1, :]).float().to(DEVICE)
    ATT_input = torch.tensor(log_spectrogram[np.newaxis, np.newaxis, :, :]).float().to(DEVICE)

    return X_input, ATT_input


def predict(real_time_data):
    # 预处理实时数据
    X_input, ATT_input = preprocess_real_time_data(real_time_data)

    # 进行推理
    with torch.no_grad():
        feat = net_lrcn(X_input)
        attention = net_att(ATT_input)
        output = net_fc(feat, attention)

    # 获取预测结果
    pred = torch.argmax(output, dim=1).item()

    return pred


def process_csv_file(file_path):
    # 读取CSV文件，假设只有一列数据且没有列名
    data = pd.read_csv(file_path, header=None)

    # 获取数据列
    ppg_values = data.iloc[:, 0].values

    # 去除前后五秒的数据（采样率为64Hz，5秒对应320个数据点）
    ppg_values = ppg_values[320:-320]

    # 总窗口大小和滑动步长
    total_window_size = 1600
    slide_step = 64

    # 初始化情绪统计
    emotion_counts = {0: 0, 1: 0, 2: 0, 3: 0}  # 假设有4种情绪类别

    # 进行滑动窗口预测
    for i in range(0, len(ppg_values) - total_window_size + 1, slide_step):
        real_time_data = ppg_values[i:i + total_window_size]
        predicted_class = predict(real_time_data)
        print(f"Predicted class: {predicted_class} at index: {i}")

        # 统计情绪
        emotion_counts[predicted_class] += 1

    # 计算每种情绪的占比
    total_predictions = sum(emotion_counts.values())
    emotion_percentages = {emotion: count / total_predictions * 100 for emotion, count in emotion_counts.items()}

    # 情绪标签映射
    emotion_labels = {0: "困惑", 1: "中性", 2: "无聊", 3: "专注"}

    print("Emotion percentages:")
    for emotion, percentage in emotion_percentages.items():
        print(f"Emotion {emotion_labels[emotion]}: {percentage:.2f}%")

# 0 困惑 1 专注 2 无聊 3 中性
# 1 2 3 4 5 6 7 8 9 10 11 12
# 困惑：1  4  7  10
# 专注：2  5  8  11
# 无聊：3  9
# 中性：6  12
# label_dict = {'Confused': 1, 'Neutral': 2, 'Bored': 3,'focus':4}
if __name__ == '__main__':
    # file_path = 'E:\\E4CODE\\Attention-LRCN-main\\12_PPGData\\P38-04-ppg.csv'  # 替换为你的CSV文件路径
    file_path = './P54-07-ppg.csv'  # 替换为你的CSV文件路径
    process_csv_file(file_path)