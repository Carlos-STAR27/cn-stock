import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def init_db():
    print("🚀 开始初始化 TiDB 数据库表结构...")
    
    # 获取数据库配置
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', 3306))
    db_user = os.getenv('DB_USER', 'root')
    db_password = os.getenv('DB_PASSWORD', '')
    db_name = os.getenv('DB_NAME', 'cn_stock')
    ssl_ca = os.getenv('TIDB_CA_PATH', '/etc/ssl/cert.pem')

    # 构建连接参数
    connect_args = {}
    if 'tidbcloud' in db_host:
        print("检测到 TiDB Cloud 环境，启用 SSL 连接...")
        connect_args['ssl'] = {'ca': ssl_ca, 'check_hostname': False}
    
    # 创建引擎
    db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(db_url, connect_args=connect_args)

    try:
        with engine.connect() as conn:
            # 1. 创建 stock_name 表
            print("正在创建 stock_name 表...")
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_name (
                ts_code VARCHAR(20) PRIMARY KEY COMMENT '股票代码',
                ts_code_name VARCHAR(50) COMMENT '股票名称'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """))

            # 2. 创建 cn_stock_daily 表
            print("正在创建 cn_stock_daily 表...")
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cn_stock_daily (
                ts_code VARCHAR(20) NOT NULL COMMENT '股票代码',
                trade_date DATE NOT NULL COMMENT '交易日期',
                price_open DECIMAL(20, 4) COMMENT '开盘价',
                price_high DECIMAL(20, 4) COMMENT '最高价',
                price_low DECIMAL(20, 4) COMMENT '最低价',
                price_close DECIMAL(20, 4) COMMENT '收盘价',
                price_pre_close DECIMAL(20, 4) COMMENT '昨收价',
                amt_chg DECIMAL(20, 4) COMMENT '涨跌额',
                pct_chg DECIMAL(20, 4) COMMENT '涨跌幅',
                vol DECIMAL(20, 4) COMMENT '成交量',
                amount DECIMAL(20, 4) COMMENT '成交额',
                PRIMARY KEY (ts_code, trade_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """))

            # 3. 创建 stock_selected 表
            print("正在创建 stock_selected 表...")
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_selected (
                execute_date DATE NOT NULL COMMENT '选股执行日期',
                execute_time TIME NOT NULL COMMENT '选股执行时间',
                ts_code VARCHAR(20) NOT NULL COMMENT '股票代码',
                trade_date DATE NOT NULL COMMENT '交易日期',
                stock_name VARCHAR(50) COMMENT '股票名称',
                price_open DECIMAL(20, 4),
                price_high DECIMAL(20, 4),
                price_low DECIMAL(20, 4),
                price_close DECIMAL(20, 4),
                price_pre_close DECIMAL(20, 4),
                amt_chg DECIMAL(20, 4),
                pct_chg DECIMAL(20, 4),
                vol DECIMAL(20, 4),
                amount DECIMAL(20, 4),
                buy_date DATE COMMENT '建议买入日期',
                gold_date DATE COMMENT 'AI观察日',
                PRIMARY KEY (execute_date, execute_time, ts_code, trade_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """))

            conn.commit()
            print("✅ 所有表结构初始化完成！")

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    init_db()
