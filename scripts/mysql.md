以下是使用 Docker Compose 快速部署 MySQL 数据库的详细指南：

### 一、基础版 docker-compose.yml
```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: edu-mysql
    environment:
      MYSQL_ROOT_PASSWORD: your_strong_password_here  # 必须设置
      MYSQL_DATABASE: edu_system  # 自动创建数据库
      MYSQL_USER: edu_admin       # 自动创建用户
      MYSQL_PASSWORD: edu_admin_password
    volumes:
      - mysql_data:/var/lib/mysql  # 数据持久化
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql  # 初始化脚本
    ports:
      - "3306:3306"
    networks:
      - edu-network

volumes:
  mysql_data:

networks:
  edu-network:
    driver: bridge
```

### 二、初始化脚本示例 (init.sql)
```sql
-- 创建应用专用用户（推荐不使用root）
CREATE USER IF NOT EXISTS 'edu_app'@'%' IDENTIFIED BY 'your_app_password';
GRANT SELECT, INSERT, UPDATE, DELETE ON edu_system.* TO 'edu_app'@'%';
FLUSH PRIVILEGES;

-- 创建测试数据（可选）
INSERT INTO users (...) VALUES (...);
```

### 三、增强版配置（生产级推荐）
```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: edu-mysql-prod
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}  # 从环境变量读取
      MYSQL_DATABASE: edu_system
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      TZ: Asia/Shanghai  # 设置时区
      MYSQL_INITDB_SKIP_TZINFO: 1  # 跳过时区表加载
    command: 
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max_connections=1000
      - --innodb_buffer_pool_size=1G
    volumes:
      - mysql_data:/var/lib/mysql
      - ./conf:/etc/mysql/conf.d  # 自定义配置
      - ./backups:/backups  # 备份目录
    ports:
      - "3306:3306"
    networks:
      - edu-network
    restart: unless-stopped  # 自动重启策略
    healthcheck:  # 健康检查
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  mysql_data:

networks:
  edu-network:
    driver: bridge
```

### 四、操作步骤

1. **准备配置文件**
   ```bash
   mkdir -p {conf,backups,init}
   echo "[mysqld]" > conf/custom.cnf
   echo "default_authentication_plugin=mysql_native_password" >> conf/custom.cnf
   ```

2. **创建 .env 文件**（安全存储凭证）
   ```env
   MYSQL_ROOT_PASSWORD=your_secure_root_password
   MYSQL_USER=edu_admin
   MYSQL_PASSWORD=admin_strong_password
   ```

3. **启动容器**
   ```bash
   docker-compose up -d
   ```

4. **验证运行状态**
   ```bash
   docker-compose ps
   docker logs edu-mysql
   ```

5. **连接数据库**
   ```bash
   docker exec -it edu-mysql mysql -u root -p
   ```

### 五、常用管理命令

| 命令                          | 说明                          |
|------------------------------|-----------------------------|
| `docker-compose stop`         | 停止容器（保留数据）             |
| `docker-compose down -v`      | 删除容器和卷（⚠️数据丢失警告）     |
| `docker exec -it edu-mysql bash` | 进入容器Shell                 |
| `docker-compose logs -f`      | 实时查看日志                   |

### 六、安全建议

1. **密码管理**
   - 使用 `openssl rand -base64 24` 生成强密码
   - 永远不要使用默认密码
   - 通过 `.env` 文件管理敏感信息，并加入 `.gitignore`

2. **网络配置**
   ```yaml
   networks:
     edu-network:
       internal: true  # 禁止外部访问
   ```

3. **SSL 加密**（在 conf/custom.cnf 中添加）
   ```ini
   [mysqld]
   ssl-ca=/etc/mysql/ssl/ca.pem
   ssl-cert=/etc/mysql/ssl/server-cert.pem
   ssl-key=/etc/mysql/ssl/server-key.pem
   ```

### 七、性能优化建议

1. **内存配置**
   ```yaml
   deploy:
     resources:
       limits:
         memory: 4G
   ```

2. **InnoDB 配置**（conf/custom.cnf）
   ```ini
   [mysqld]
   innodb_buffer_pool_size = 2G
   innodb_log_file_size = 256M
   innodb_flush_log_at_trx_commit = 2
   ```

3. **开启慢查询日志**
   ```ini
   slow_query_log = 1
   slow_query_log_file = /var/log/mysql/slow.log
   long_query_time = 1
   ```