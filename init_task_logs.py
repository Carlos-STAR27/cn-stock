import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv('.env.local')

def init_task_logs():
    print("🚀 开始创建 task_logs 表...")
    
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    ssl_ca = os.getenv('TIDB_CA_PATH')
    
    connect_args = {}
    if 'tidbcloud' in str(db_host):
        connect_args['ssl'] = {'ca': ssl_ca, 'check_hostname': False}
        
    url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(url, connect_args=connect_args)
    
    try:
        with engine.connect() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                task_name VARCHAR(50) NOT NULL COMMENT '任务名称',
                execute_time DATETIME NOT NULL COMMENT '执行时间',
                status VARCHAR(20) NOT NULL COMMENT '状态: SUCCESS/FAIL',
                message TEXT COMMENT '执行详情/错误信息',
                INDEX idx_task_time (task_name, execute_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """))
            conn.commit()
            print("✅ task_logs 表创建成功！")
    except Exception as e:
        print(f"❌ 创建失败: {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    init_task_logs()
