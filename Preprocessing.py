#存放预处理的代码
import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft

def test():
    channel_data = [517.2000122070312, 385.5, 1323.300048828125, -2052.60009765625, 787.7999877929688,
                    -63.599998474121094, -751.7999877929688, 357.0, -608.0999755859375, 359.1000061035156,
                    -426.0, 137.10000610351562, -213.3000030517578, -36.599998474121094, -678.2999877929688,
                    637.2000122070312, 100.5, 33.0, 539.7000122070312, -12.300000190734863, -2000.699951171875,
                    -11.399999618530273, -12.600000381469727, -7.800000190734863]
    # 采样率(Hz)
    sample_rate = 256

    # 转换为频域
    n = len(channel_data)
    print("n:",n)
    frequencies = np.fft.fftfreq(n, d=1 / sample_rate)
    fft_values = fft(channel_data)


    # 计算频带范围 (Hz)
    delta_band = (0.5 <= frequencies) & (frequencies < 4)
    theta_band = (4 <= frequencies) & (frequencies < 8)
    alpha_band = (8 <= frequencies) & (frequencies < 12)
    beta_band = (13 <= frequencies) & (frequencies < 30)
    gamma_band = (30 <= frequencies) & (frequencies < 100)

    # 计算每个频带的功率（功率谱密度的平方）
    delta_power = np.sum(np.abs(fft_values[delta_band]) ** 2)
    theta_power = np.sum(np.abs(fft_values[theta_band]) ** 2)
    alpha_power = np.sum(np.abs(fft_values[alpha_band]) ** 2)
    beta_power = np.sum(np.abs(fft_values[beta_band]) ** 2)
    gamma_power = np.sum(np.abs(fft_values[gamma_band]) ** 2)

    # 显示每个频带的功率
    print(f"Delta Power (0.5-4 Hz): {delta_power}")
    print(f"Theta Power (4-8 Hz): {theta_power}")
    print(f"Alpha Power (8-12 Hz): {alpha_power}")
    print(f"Beta Power (13-30 Hz): {beta_power}")
    print(f"Gamma Power (30-100 Hz): {gamma_power}")

    # 可视化频谱
    plt.plot(frequencies[:n // 2], np.abs(fft_values)[:n // 2])
    plt.title('EEG Frequency Spectrum')
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude')
    plt.grid(True)
    plt.show()


def compute_band_entropy(window_data, sample_rate=256):
    """
    计算每个频带的差分熵特征
    :param window_data: 包含多个EEGSensorData对象的窗口数据
    :param sample_rate: 采样率（Hz）
    :return: 每个频带的差分熵值字典
    """
    # 定义频带范围
    bands = {
        'Delta': (0.5, 4),    # 0.5 - 4 Hz
        'Theta': (4, 8),      # 4 - 8 Hz
        'Alpha': (8, 12),     # 8 - 12 Hz
        'Beta': (13, 30),     # 13 - 30 Hz
        'Gamma': (30, 100)    # 30 - 100 Hz
    }

    # 创建字典来存储每个频带的差分熵
    entropy_values = {}

    # 遍历每个EEGSensorData对象中的每个通道
    for i in range(len(window_data[0].channel_data)):  # 遍历每个通道
        # 提取每个通道的数据（计算幅度）
        signal = [np.abs(data.channel_data[i]) for data in window_data]

        # 将信号转换为频域
        n = len(signal)
        frequencies = np.fft.fftfreq(n, d=1/sample_rate)
        fft_values = fft(signal)

        # 计算每个频带的功率谱并计算差分熵
        band_entropy = {}
        for band_name, (low, high) in bands.items():
            # 提取频率范围对应的功率谱
            band_mask = (frequencies >= low) & (frequencies < high)
            band_values = np.abs(fft_values[band_mask]) ** 2  # 计算功率谱（幅度的平方）

            # 计算标准差并计算差分熵
            std_dev = np.std(band_values)
            entropy_value = 0.5 * np.log(2 * np.pi * np.e * std_dev ** 2)
            band_entropy[band_name] = entropy_value

        # 将每个通道的频带差分熵存储到字典中
        entropy_values[f'Channel_{i + 1}'] = band_entropy

    return entropy_values