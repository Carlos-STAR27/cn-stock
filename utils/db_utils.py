import os
from sqlalchemy import create_engine, text
from datetime import datetime
import traceback
from dotenv import load_dotenv
import certifi

# 加载环境变量 (优先加载 .env, 然后 .env.local)
load_dotenv()
load_dotenv('.env.local')

def get_config(key, default=None):
    """
    获取配置项，支持从 os.environ 或 streamlit.secrets 获取
    """
    # 1. 尝试从环境变量获取
    val = os.getenv(key)
    if val is not None:
        return val
    
    # 2. 尝试从 streamlit.secrets 获取 (仅在 Streamlit 环境下有效)
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except ImportError:
        pass
    except Exception:
        pass # st.secrets 访问可能在非 Streamlit 运行时报错
        
    return default

def get_db_engine():
    """获取数据库连接引擎"""
    db_host = get_config('DB_HOST')
    db_port = get_config('DB_PORT', 3306)
    db_user = get_config('DB_USER')
    db_password = get_config('DB_PASSWORD')
    db_name = get_config('DB_NAME')
    
    # SSL 配置
    ssl_ca = get_config('TIDB_CA_PATH')
    
    # 如果指定了 CA 路径但文件不存在 (常见于云端环境配置不一致)，则强制使用 certifi
    if ssl_ca and not os.path.exists(ssl_ca):
        print(f"⚠️ Warning: Configured TIDB_CA_PATH '{ssl_ca}' not found. Falling back to certifi.")
        ssl_ca = None

    # 如果未指定 CA 路径 (或路径无效)，尝试使用 certifi 的默认路径 (适用于 Streamlit Cloud 等环境)
    if not ssl_ca:
        ssl_ca = certifi.where()
    
    connect_args = {}
    if db_host and 'tidbcloud' in db_host:
        connect_args['ssl'] = {'ca': ssl_ca, 'check_hostname': False}
    
    # 确保端口是整数
    try:
        db_port = int(db_port)
    except (ValueError, TypeError):
        db_port = 3306
        
    url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    # 增加连接池配置，提高稳定性
    return create_engine(
        url, 
        connect_args=connect_args,
        pool_pre_ping=True,  # 自动检测断开的连接
        pool_recycle=3600    # 1小时回收连接
    )

def get_db_config_debug():
    """
    返回数据库配置的调试信息 (仅用于诊断 SSL 路径问题)
    """
    debug_info = {}
    
    # 1. 原始配置的 CA 路径
    raw_ssl_ca = get_config('TIDB_CA_PATH')
    debug_info['raw_ssl_ca'] = raw_ssl_ca
    
    # 2. 检查原始路径是否存在
    if raw_ssl_ca:
        debug_info['raw_ssl_ca_exists'] = os.path.exists(raw_ssl_ca)
    else:
        debug_info['raw_ssl_ca_exists'] = None
        
    # 3. 最终使用的 CA 路径
    ssl_ca = raw_ssl_ca
    if ssl_ca and not os.path.exists(ssl_ca):
        ssl_ca = None
    if not ssl_ca:
        ssl_ca = certifi.where()
        
    debug_info['final_ssl_ca'] = ssl_ca
    debug_info['final_ssl_ca_exists'] = os.path.exists(ssl_ca)
    debug_info['certifi_where'] = certifi.where()
    
    return debug_info

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
