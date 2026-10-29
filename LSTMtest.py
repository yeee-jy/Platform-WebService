from LinkPostgreSQL import test
import numpy as np
from sklearn.model_selection import train_test_split
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import joblib
import matplotlib.pyplot as plt


# 定义LSTM模型
class LSTMModel(nn.Module):
    def __init__(self, input_size=24, hidden_size=64, num_layers=2, output_size=1):
        super(LSTMModel, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        # 处理2D输入 (batch_size, input_size)
        if x.dim() == 2:
            x = x.unsqueeze(1)  # 变为 (batch_size, 1, input_size)

        # x.shape: (batch_size, seq_len, input_size)
        lstm_out, _ = self.lstm(x)

        # 获取最后时间步的输出
        last_time_step_out = lstm_out[:, -1, :]
        output = self.fc(last_time_step_out)
        return output


# 提取数据
def extract_data(data):
    """
    从EEG数据中提取特征（channelData）和标签（trigger）
    :param data: EEG 数据对象列表，每个对象是 EEGSensorData 实例
    :return: 特征矩阵和标签数组
    """
    # 使用点符号访问属性
    features = [entry.channel_data for entry in data]  # 访问 channel_data 属性
    labels = [entry.trigger for entry in data]         # 访问 trigger 属性
    return np.array(features), np.array(labels)


# 训练和评估模型
def train_and_evaluate_model(train_loader, test_loader, model, criterion, optimizer, num_epochs, device):
    """
    训练并评估模型
    """
    model.to(device)

    # 记录训练过程中的损失和准确率
    train_losses = []
    train_accs = []
    test_losses = []
    test_accs = []

    for epoch in range(num_epochs):
        # --- 训练阶段 ---
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)

            # 清零梯度
            optimizer.zero_grad()

            # 前向传播
            outputs = model(inputs)
            loss = criterion(outputs, labels)

            # 反向传播和优化
            loss.backward()
            optimizer.step()

            # 统计损失和准确率
            running_loss += loss.item() * inputs.size(0)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        epoch_loss = running_loss / total
        epoch_acc = correct / total
        train_losses.append(epoch_loss)
        train_accs.append(epoch_acc)

        # --- 评估阶段 ---
        model.eval()
        running_loss = 0.0
        correct = 0
        total = 0

        # 评估时不计算梯度
        with torch.no_grad():
            for inputs, labels in test_loader:
                inputs, labels = inputs.to(device), labels.to(device)

                outputs = model(inputs)
                loss = criterion(outputs, labels)

                running_loss += loss.item() * inputs.size(0)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        epoch_loss = running_loss / total
        epoch_acc = correct / total
        test_losses.append(epoch_loss)
        test_accs.append(epoch_acc)

        print(f'Epoch [{epoch + 1}/{num_epochs}], '
              f'Train Loss: {train_losses[-1]:.4f}, Train Acc: {train_accs[-1]:.4f}, '
              f'Test Loss: {test_losses[-1]:.4f}, Test Acc: {test_accs[-1]:.4f}')

    # 绘制训练曲线
    plt.figure(figsize=(12, 4))

    plt.subplot(1, 2, 1)
    plt.plot(train_losses, label='Train Loss')
    plt.plot(test_losses, label='Test Loss')
    plt.title('Loss Curve')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(train_accs, label='Train Accuracy')
    plt.plot(test_accs, label='Test Accuracy')
    plt.title('Accuracy Curve')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.legend()

    plt.tight_layout()
    plt.show()

    return model, train_losses, train_accs, test_losses, test_accs


def try_add_model():
    # 1. 获取并处理数据
    print("Loading data...")
    data = test()  # 获取数据
    if not data:
        print("Error: No data received from test().")
        return

    print(f"Data loaded. Number of samples: {len(data)}")

    features, labels = extract_data(data)  # 提取特征和标签
    print(f"Features shape: {features.shape}")
    print(f"Labels shape: {labels.shape}")
    print(f"Unique labels: {np.unique(labels)}")

    # 2. 分割数据为训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42, stratify=labels  # 使用 stratify 保证类别分布
    )

    # 3. 将数据转换为 Tensor 并创建 DataLoader
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
    X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
    y_train_tensor = torch.tensor(y_train, dtype=torch.long)
    y_test_tensor = torch.tensor(y_test, dtype=torch.long)

    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    test_dataset = TensorDataset(X_test_tensor, y_test_tensor)

    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)  # 调整 batch_size
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

    # 4. 定义模型参数
    input_dim = features.shape[1]  # 从数据中自动获取输入维度（通道数）
    hidden_dim = 64
    num_layers = 2
    output_dim = len(np.unique(labels))  # 类别数量

    print(f"Model parameters - Input dim: {input_dim}, Hidden dim: {hidden_dim}, Output dim: {output_dim}")

    # 5. 初始化模型、损失函数和优化器
    model = LSTMModel(input_size=input_dim, hidden_size=hidden_dim, num_layers=num_layers, output_size=output_dim)

    # 选择设备（GPU 如果可用）
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # 损失函数和优化器
    criterion = nn.CrossEntropyLoss()  # 交叉熵损失，适用于分类问题
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)  # Adam 优化器

    # 6. 训练模型
    print("Starting training...")
    num_epochs = 50  # 训练轮数
    trained_model, train_losses, train_accs, test_losses, test_accs = train_and_evaluate_model(
        train_loader, test_loader, model, criterion, optimizer, num_epochs, device
    )

    # 7. 保存模型
    model_filename = 'models/lstm_eeg_model.pth'
    torch.save(trained_model.state_dict(), model_filename)
    print(f"Model saved to {model_filename}")
    print("Training history saved to training_history.pkl")


# 2. 定义预测函数
def predict_with_trained_model(model_path, new_data, input_dim, hidden_dim, num_layers, output_dim):
    """
    使用训练好的模型对新数据进行预测。

    Args:
        model_path (str): 训练好的模型权重文件路径 (.pth)。
        new_data (np.ndarray): 待预测的新数据，形状应为 (num_samples, seq_len, input_dim)。
        input_dim (int): 输入特征的维度（通道数）。
        hidden_dim (int): LSTM隐藏层的维度。
        num_layers (int): LSTM的层数。
        output_dim (int): 输出类别的数量。

    Returns:
        np.ndarray: 预测的类别标签，形状为 (num_samples,)。
    """
    # 检查新数据形状
    if len(new_data.shape) == 2:
        # 将 (num_samples, input_dim) 转换为 (num_samples, 1, input_dim)
        new_data = new_data.reshape(new_data.shape[0], 1, new_data.shape[1])
        print(f"Reshaped input data to 3D: {new_data.shape}")

    if len(new_data.shape) != 3:
        raise ValueError(f"新数据的形状应为 (num_samples, seq_len, input_dim)，但收到的是 {new_data.shape}")

    if new_data.shape[2] != input_dim:
        raise ValueError(f"新数据的输入维度应为 {input_dim}，但收到的是 {new_data.shape[2]}")

    # 选择设备
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device} for prediction.")

    # 初始化模型并加载权重
    model = LSTMModel(input_size=input_dim, hidden_size=hidden_dim, num_layers=num_layers, output_size=output_dim)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()  # 设置为评估模式

    # 数据预处理：转换为Tensor
    new_data_tensor = torch.tensor(new_data, dtype=torch.float32).to(device)

    # 执行预测（不计算梯度）
    with torch.no_grad():
        outputs = model(new_data_tensor)
        # 获取预测概率最高的类别索引
        _, predicted_labels = torch.max(outputs, 1)

    # 将结果从Tensor转换为numpy数组并返回
    return predicted_labels.cpu().numpy()


# 3. 演示如何使用预测函数
def try_predict_on_new_data():

    # --- 模型和数据参数 ---
    MODEL_PATH = "models/lstm_eeg_model.pth"
    INPUT_DIM = 24  # 每个时间步的特征数（通道数）
    HIDDEN_DIM = 64  # LSTM隐藏层维度
    NUM_LAYERS = 2  # LSTM层数
    OUTPUT_DIM = 1  # 类别数量（假设是二分类问题）

    print("Preparing new test data...")
    # 从你的数据库中获取新数据
    try:
        new_raw_data = test()
        if not new_raw_data:
            print("Warning: No new data received from test(). Using synthetic data for demonstration.")
            raise ValueError("No real data")

        # 提取特征
        new_features = np.array([entry['channel_data'] for entry in new_raw_data])
        # 将2D数据扩展为3D (samples, seq_len=1, features)
        new_features = new_features.reshape(new_features.shape[0], 1, new_features.shape[1])
        # 为了验证，我们也提取真实标签
        true_labels = np.array([entry['trigger_value'] for entry in new_raw_data])
        print(f"Successfully loaded {new_features.shape[0]} new samples from database.")

    except Exception as e:
        print(f"Using synthetic data for demonstration: {e}")
        NUM_SYNTHETIC_SAMPLES = 5
        SEQ_LEN = 100  # 假设每个样本的时间步长为100
        new_features = np.random.randn(NUM_SYNTHETIC_SAMPLES, SEQ_LEN, INPUT_DIM).astype(np.float32)
        true_labels = np.random.randint(0, OUTPUT_DIM, size=NUM_SYNTHETIC_SAMPLES)
        print(f"Generated {NUM_SYNTHETIC_SAMPLES} synthetic samples.")

    print(f"New features shape: {new_features.shape}")

    # --- 调用预测函数 ---
    print("\nStarting prediction...")
    predicted_labels = predict_with_trained_model(
        model_path=MODEL_PATH,
        new_data=new_features,
        input_dim=INPUT_DIM,
        hidden_dim=HIDDEN_DIM,
        num_layers=NUM_LAYERS,
        output_dim=OUTPUT_DIM
    )

    # --- 打印和分析结果 ---
    print("\nPrediction Results:")
    print("-" * 30)
    for i in range(len(predicted_labels)):
        pred_label = predicted_labels[i]
        true_label = true_labels[i] if 'true_labels' in locals() else "N/A"
        print(f"Sample {i + 1}: Predicted Label = {pred_label}, True Label = {true_label}")

    if 'true_labels' in locals() and len(true_labels) > 0:
        accuracy = np.mean(predicted_labels == true_labels)
        print("-" * 30)
        print(f"Overall Prediction Accuracy on New Data: {accuracy:.4f}")

# 接收实时的数据
def predict_single_data(new_data, model, device):
    """
    将单条 EEG 数据传入 LSTM 模型进行推理并返回预测结果。
    :param new_data: 一个单独的 EEG 数据对象（EEGSensorData）
    :param model: 训练好的 LSTM 模型
    :param device: 使用的设备（CPU 或 GPU）
    :return: 预测的标签
    """
    # 提取特征
    features, _ = extract_data([new_data])  # 传入单条数据，提取特征

    # 将特征转换为 Tensor 并送入模型
    features = torch.tensor(features, dtype=torch.float32).to(device)

    # 使用模型进行推理
    with torch.no_grad():
        model.eval()  # 设置为评估模式
        outputs = model(features)  # 获得模型输出
        _, predicted_labels = torch.max(outputs, 1)  # 获取预测的标签

    return predicted_labels.cpu().numpy()  # 返回预测标签


def try_predict_on_new_data(new_data):
    # 模型路径和设备
    MODEL_PATH = "models/lstm_eeg_model.pth"
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # 加载训练好的模型
    model = LSTMModel(input_size=24, hidden_size=64, num_layers=2, output_size=1)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model.to(device)

    # 进行推理并获取预测结果
    predicted_label = predict_single_data(new_data, model, device)

    # 输出最终的预测结果
    print(f"最终识别结果: {predicted_label}")
# 调用主函数
if __name__ == "__main__":
    try_predict_on_new_data()

    # try_add_model()