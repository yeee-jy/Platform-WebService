import psycopg2
import traceback  # 用于打印完整异常栈
import struct
from datetime import datetime, timedelta

def watchAllSQL(cur):
    print("\n当前数据库的所有表：")
    cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """)
    tables = cur.fetchall()   # ★ 一定要 fetch 出结果
    for t in tables:
        print(" -", t[0])

def show_all_course(cur):
    print("\ncourse 表中的所有数据：")
    cur.execute("""
        SELECT id, course_name, teacher, credit, class_hour, create_time
        FROM course;
    """)
    rows = cur.fetchall()

    if not rows:
        print("（当前表中没有数据）")
        return

    for row in rows:
        print(row)

# 创建一个表
def create_table(conn, cur):
    print("\n创建表：")
    # 创建两个表， egg_metadaya:存储实验参数，eeg_data:存储时序EEG数据
    """
        id:系统自己增加
        subject_id：受试者名称
        experiment_date：实验时间
        sampling_rate：采样率
        channel_count：通道数
        notes：备注信息
    """
    egg_metadata = """
            CREATE TABLE IF NOT EXISTS egg_metadata (
                id SERIAL PRIMARY KEY,  
                subject_id VARCHAR(50) NOT NULL,
                experiment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sampling_rate INT,
                channel_count INT,
                notes TEXT
            );
            """

    cur.execute(egg_metadata)
    # 创建 eeg_data 表
    """
        id:自增id
        timestamp：时序字段
        metadata_id：关联到元数据表id
        adc_status：传感器状态，ADC状态
        channel_data：多通道EEG数据
        trigger_value：触发器的值
        notes：备注值
    """
    eeg_data = """
               CREATE TABLE IF NOT EXISTS eeg_data
               (
                   id            SERIAL,
                   timestamp     TIMESTAMPTZ NOT NULL,
                   metadata_id   INT         NOT NULL, 
                   adc_status    INT,  
                   channel_data  DOUBLE PRECISION[], 
                   trigger_value DOUBLE PRECISION,  
                   notes         TEXT,
                   -- 定义外键约束，确保 metadata_id 在 egg_metadaya 表中存在 
                   FOREIGN KEY (metadata_id) REFERENCES egg_metadata (id)
               ); 
               """
    cur.execute(eeg_data)

    #普通表eeg_data转为TimescaleDB超表，并且以 'timestamp' 列作为分区的依据
    convert_to_hypertable_sql = """
        SELECT create_hypertable('eeg_data', 'timestamp');
    """
    try:
        cur.execute(convert_to_hypertable_sql)
        print("成功将 eeg_data 转换为超表！")
    except Exception as e:
        if "already a hypertable" in str(e):
            print("表 eeg_data 已经是超表，无需重复转换。")
        else:
            # 如果是其他错误，我们再抛出
            raise

    # 提交所有更改
    conn.commit()
    print("创建成功。")


def connect_postgres():
    conn = None
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="postgres",
            user="postgres",
            password=123,  # 如果能连上就先不改
            connect_timeout=10
        )
        print("连接成功！")

        cur = conn.cursor()
        # 创建两个表， egg_metadaya:存储实验参数，eeg_data:存储时序EEG数据
        create_table(conn, cur)
        cur.close()
        return conn


    except Exception as e:
        print("连接失败，详细错误：")
        print(f"错误类型：{type(e).__name__}")
        print(f"错误描述：{str(e)}")
        print("完整异常栈：")
        traceback.print_exc()

def batch_insert_to_db(conn, metadata_id, window_data):
    """
    批量将滑动窗口数据插入到 TimescaleDB 的 eeg_data 表中
    :param conn: 数据库连接对象
    :param metadata_id: 关联的元数据 ID
    :param window_data: 完整滑动窗口的数据列表（包含多个 EEGSensorData 对象）
    :return: bool，插入成功返回 True，失败返回 False
    """
    if not conn:
        print("[DB ERROR] 数据库连接为空，无法插入数据")
        return False
    if not metadata_id:
        print("[DB ERROR] metadata_id 为空，无法插入数据")
        return False
    if not window_data:
        print("[DB WARNING] 窗口数据为空，无需插入")
        return True

    # SQL 插入语句
    insert_sql = """
            INSERT INTO eeg_data (
                timestamp, 
                metadata_id, 
                adc_status, 
                channel_data, 
                trigger_value
            ) VALUES (%s, %s, %s, %s, %s);
        """

    try:
        # 准备批量插入的数据（转换为 SQL 所需的元组列表）
        data_to_insert = [
            (
                data.timestamp,    # 时间戳（已转换为 datetime 对象）
                metadata_id,       # 关联元数据 ID
                struct.unpack('>Q', b'\x00\x00' + data.adc_status)[0] if isinstance(data.adc_status, bytes) else int(data.adc_status),
                data.channel_data,  # 多通道数据（列表自动转 PostgreSQL 数组）
                data.trigger       # 触发器值
            )
            for data in window_data
        ]

        # 执行批量插入
        cur = conn.cursor()
        cur.executemany(insert_sql, data_to_insert)
        conn.commit()
        print(f"[DB SUCCESS] 成功插入 {len(data_to_insert)} 条数据（metadata_id: {metadata_id}）")
        cur.close()
        return True

    except Exception as e:
        # 插入失败回滚事务
        conn.rollback()
        print(f"[DB ERROR] 批量插入失败: {str(e)}")
        if 'cur' in locals():  # 确保游标关闭
            cur.close()
        return False

# 先创建元数据表
def create_or_get_metadata(conn, subject_id="default_subject", sampling_rate=None, channel_count=None,
                           notes="auto_created"):
    """
    自动创建元数据记录（如果不存在），并返回对应的 metadata_id
    """
    if not conn:
        print("[Metadata ERROR] 数据库连接为空。")
        return None
    try:
        cur = conn.cursor()
        # 先查询是否已有记录
        cur.execute("SELECT id FROM egg_metadata WHERE subject_id = %s ORDER BY experiment_date DESC LIMIT 1;",
                    (subject_id,))
        result = cur.fetchone()
        if result:
            metadata_id = result[0]
            print(f"[Metadata] 找到现有元数据，ID: {metadata_id}")
            cur.close()
            return metadata_id

        # 如果没有，就创建一条新记录
        cur.execute("""
                    INSERT INTO egg_metadata (subject_id, sampling_rate, channel_count, notes)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                    """, (subject_id, sampling_rate, channel_count, notes))

        metadata_id = cur.fetchone()[0]
        conn.commit()
        print(f"[Metadata] 创建新元数据，ID: {metadata_id}")
        cur.close()
        return metadata_id
    except Exception as e:
        print(f"[Metadata ERROR] 创建/查询失败: {e}")
        conn.rollback()
        return None

# 查询数据
def query_data_by_time_range(conn, subject_id, start_time, end_time):
    """
    根据受试者ID和时间范围查询对应的EEG数据。
    :param conn: 一个已经建立好的 psycopg2 数据库连接对象。
    :param subject_id: 受试者ID (例如 'sub-001')。
    :param start_time: 开始时间 (datetime 对象或可被 PostgreSQL 解析的字符串)。
    :param end_time: 结束时间 (datetime 对象或可被 PostgreSQL 解析的字符串)。
    :return: 查询结果列表，每个元素是一个字典，包含一行数据。
             如果查询失败，返回 None。
    """
    if conn is None or conn.closed:
        print("[DB ERROR] 数据库连接无效或已关闭。")
        return None

    cur = None
    try:
        cur = conn.cursor()

        # 1. 先根据 subject_id 查找对应的 metadata_id
        metadata_query = """
            SELECT id 
            FROM egg_metadata 
            WHERE subject_id = %s;
        """
        cur.execute(metadata_query, (subject_id,))
        metadata_result = cur.fetchone()

        if not metadata_result:
            print(f"[DB ERROR] 未找到 subject_id 为 '{subject_id}' 的元数据记录。")
            cur.close()
            return None

        metadata_id = metadata_result[0]
        print(f"[DB INFO] 找到 subject_id '{subject_id}' 对应的 metadata_id: {metadata_id}")

        # 2. 再用 metadata_id 和时间范围查询 eeg_data
        data_query = """
            SELECT 
                id, 
                timestamp, 
                metadata_id, 
                adc_status, 
                channel_data, 
                trigger_value, 
                notes
            FROM 
                eeg_data
            WHERE 
                metadata_id = %s 
                AND timestamp BETWEEN %s AND %s
            ORDER BY 
                timestamp ASC;
        """
        cur.execute(data_query, (metadata_id, start_time, end_time))

        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur.fetchall()]

        cur.close()
        return results

    except Exception as e:
        print(f"[DB ERROR] 查询数据失败: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if cur and not cur.closed:
            cur.close()

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

    # 3. 执行查询
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

