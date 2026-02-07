import os
from sqlalchemy import create_engine, text
from datetime import datetime
import traceback
from dotenv import load_dotenv

# 加载环境变量 (优先加载 .env, 然后 .env.local)
load_dotenv()
load_dotenv('.env.local')

def get_db_engine():
    """获取数据库连接引擎"""
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT', 3306)
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    ssl_ca = os.getenv('TIDB_CA_PATH')
    
    connect_args = {}
    if db_host and 'tidbcloud' in db_host:
        connect_args['ssl'] = {'ca': ssl_ca, 'check_hostname': False}
        
    url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(url, connect_args=connect_args)

def log_task_execution(task_name, status, message=""):
    """记录任务执行日志"""
    engine = get_db_engine()
    try:
        with engine.connect() as conn:
            # 截断过长的消息
            if len(message) > 65535:
                message = message[:65530] + "..."
                
            sql = text("""
            INSERT INTO task_logs (task_name, execute_time, status, message)
            VALUES (:task_name, :execute_time, :status, :message)
            """)
            conn.execute(sql, {
                "task_name": task_name,
                "execute_time": datetime.now(),
                "status": status,
                "message": message
            })
            conn.commit()
    except Exception as e:
        print(f"❌ 写入日志失败: {e}")
        traceback.print_exc()
    finally:
        engine.dispose()
