# 多模态数据采集与学习者状态实时感知平台 - 中心服务器

## Fast API Web Service

## Dokcer容器部署服务

### RabbitMQ 消息队列

### PostgreSQL 数据库
>id:10001
sub.py文件 接受来自学生端的EEG数据，callback函数接收到的数据，并调用batch_insert_to_db（）函数存储 数据库中

> 数据库结构：

eeg_data:存储EEG原始数据

    id:自增id
    timestamp：时序字段
    metadata_id：关联到元数据表id
    adc_status：传感器状态，ADC状态
    channel_data：多通道EEG数据
    trigger_value：触发器的值
    notes：备注值

eeg_metadate:存储元数据,每次采集数据时，会生成一个元数据，用于关联eeg_data表

    id:系统自己增加
    subject_id：受试者名称
    experiment_date：实验时间
    sampling_rate：采样率
    channel_count：通道数
    notes：备注信息

使用规则：

记录：

    首先需要修改sub.py文件中的受试者信息：姓名、采样率、通道数，
    以便创建受试者的元信息，用于记录
    
    然后运行sub.py文件，运行成功后，会自动启动RabbitMQ消息队列，并开始接收来自学生端的EEG数据
    
    并且可以根据需求，在初始化的时候进行滑动窗口的设置，set_sliding_window(sliding_size)，设置滑动窗口的大小，目前默认是10s无重叠的滑动窗口

```py
#具体代码参考
def callback(ch, method, properties, body, conn,metadata_id):
    if properties.content_type == 'application/json':
        print("Received JSON message:")
        print(body.decode())
    elif properties.content_type == 'application/msgpack':
        # 目前服务器接收的是这个msgpack格式
        print("Received binary message:")

        array = msgpack.unpackb(body)
        for item in array:
            data = deserialize_sensor(item)
            # 接收学生端传入的代码，自动的调用当前的回调函数
            utilis.add_data(data,conn,metadata_id)

    print("------------------------------------")
```

查找：

    运行LinkPostgreSQL.py文件中的def query_data_by_time_range函数
    参数：数据库名称，受试者名称，开始时间、结束时间，返回指定时间段内的数据
    数据格式为（样本点数，EEGSensorData),EEGSensorData的具体格式参考sub.py文件

```py
#查询代码参考
def test():
    # 1. 建立数据库连接
    conn = connect_postgres()
    if not conn:
        exit()

    # 2. 定义查询条件
    subject_id = "sub-001"  # 你的受试者ID
    # 设置查询的时间范围
    start_time = datetime(2025, 11, 21, 16, 45, 57, 540000)
    end_time = datetime(2025, 11, 21, 16, 45, 57, 590000)

    # 3. 执行查询，具体的查询函数
    """
        根据受试者ID和时间范围查询对应的EEG数据。
        :param conn: 一个已经建立好的 psycopg2 数据库连接对象。
        :param subject_id: 受试者ID (例如 'sub-001')。
        :param start_time: 开始时间 (datetime 对象或可被 PostgreSQL 解析的字符串)。
        :param end_time: 结束时间 (datetime 对象或可被 PostgreSQL 解析的字符串)。
        :return: 查询结果列表，每个元素是一个字典，包含一行数据。
                 如果查询失败，返回 None。
    """
    data = query_data_by_time_range(conn, subject_id, start_time, end_time)

    # 4. 处理结果
    if data:
        print(f"\n成功查询到 {len(data)} 条记录:")
        for record in data:
            print(f"  - 时间: {record['timestamp']}, ADC状态: {record['adc_status']}")
    else:
        print("未查询到数据或查询失败。")

    # 5. 关闭连接
    conn.close()
    return data
#返回的查询结果是原始的EEG数据，结构为 采样点数 X 24通道数
```

结果：

目前测试的方式是，每收到一个Data数据都直接的送进模型进行推理，并且之后进行存储数据库中，暂时设置的滑动窗口为10s，每存储10s数据，缓存进入数据库，并且也可以做其它特征提取（暂时只尝试DE特征）

```
[Utils] 整数时间戳 1764125843151 已成功转换为: 2025-11-26 10:57:23.151000
最终识别结果: [0]
[ADD] 收到新数据，时间: 2025-11-26 10:57:23.151000。缓冲区现在有 184 条数据。
[SCOPE] 当前窗口时间范围: 2025-11-26 10:57:22.541000 ~ 2025-11-26 10:57:32.541000
[Utils] 缓冲区数据尚未填满一个窗口，继续等待...
[ALL_DATA] 目前一共存储的滑动窗口的数量：0

[Utils] 整数时间戳 1764125843154 已成功转换为: 2025-11-26 10:57:23.154000
最终识别结果: [0]
[ADD] 收到新数据，时间: 2025-11-26 10:57:23.154000。缓冲区现在有 185 条数据。
[SCOPE] 当前窗口时间范围: 2025-11-26 10:57:22.541000 ~ 2025-11-26 10:57:32.541000
[Utils] 缓冲区数据尚未填满一个窗口，继续等待...
[ALL_DATA] 目前一共存储的滑动窗口的数量：0

[Utils] 整数时间戳 1764125843158 已成功转换为: 2025-11-26 10:57:23.158000
最终识别结果: [0]
[ADD] 收到新数据，时间: 2025-11-26 10:57:23.158000。缓冲区现在有 186 条数据。
[SCOPE] 当前窗口时间范围: 2025-11-26 10:57:22.541000 ~ 2025-11-26 10:57:32.541000
[Utils] 缓冲区数据尚未填满一个窗口，继续等待...
[ALL_DATA] 目前一共存储的滑动窗口的数量：0

[Utils] 整数时间戳 1764125843161 已成功转换为: 2025-11-26 10:57:23.161000
最终识别结果: [0]
[ADD] 收到新数据，时间: 2025-11-26 10:57:23.161000。缓冲区现在有 187 条数据。
[SCOPE] 当前窗口时间范围: 2025-11-26 10:57:22.541000 ~ 2025-11-26 10:57:32.541000
[Utils] 缓冲区数据尚未填满一个窗口，继续等待...
[ALL_DATA] 目前一共存储的滑动窗口的数量：0

[Utils] 整数时间戳 1764125843164 已成功转换为: 2025-11-26 10:57:23.164000
最终识别结果: [0]
[ADD] 收到新数据，时间: 2025-11-26 10:57:23.164000。缓冲区现在有 188 条数据。
[SCOPE] 当前窗口时间范围: 2025-11-26 10:57:22.541000 ~ 2025-11-26 10:57:32.541000
[Utils] 缓冲区数据尚未填满一个窗口，继续等待...
[ALL_DATA] 目前一共存储的滑动窗口的数量：0

[Utils] 整数时间戳 1764125843168 已成功转换为: 2025-11-26 10:57:23.168000
最终识别结果: [0]
[ADD] 收到新数据，时间: 2025-11-26 10:57:23.168000。缓冲区现在有 189 条数据。
[SCOPE] 当前窗口时间范围: 2025-11-26 10:57:22.541000 ~ 2025-11-26 10:57:32.541000
[Utils] 缓冲区数据尚未填满一个窗口，继续等待...
[ALL_DATA] 目前一共存储的滑动窗口的数量：0
```

### 流媒体服务

### NGINX反向代理