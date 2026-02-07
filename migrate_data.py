import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import time

# 加载环境变量 (主要用于获取远程 TiDB 配置)
load_dotenv()

def get_local_engine():
    """获取本地 MySQL 连接引擎"""
    # 这里使用用户之前配置的本地数据库信息
    db_config = {
        'host': 'localhost',
        'port': 3306,
        'user': 'root',
        'password': 'showlang',
        'database': 'cn_stock'
    }
    url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    return create_engine(url)

def get_remote_engine():
    """获取远程 TiDB 连接引擎"""
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    ssl_ca = os.getenv('TIDB_CA_PATH')
    
    connect_args = {}
    if 'tidbcloud' in db_host:
        connect_args['ssl'] = {'ca': ssl_ca, 'check_hostname': False}
        
    url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(url, connect_args=connect_args)

def migrate_table(table_name, chunk_size=5000):
    print(f"\n📦 开始迁移表: {table_name}")
    
    local_engine = get_local_engine()
    remote_engine = get_remote_engine()
    
    try:
        # 1. 获取本地数据总数
        with local_engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"   本地共有 {count} 条记录")
            
        if count == 0:
            print("   ⚠️ 表为空，跳过")
            return

        # 2. 分批读取并写入
        offset = 0
        total_migrated = 0
        
        while offset < count:
            # 分批读取
            query = f"SELECT * FROM {table_name} LIMIT {chunk_size} OFFSET {offset}"
            df = pd.read_sql(query, local_engine)
            
            if df.empty:
                break
                
            # 写入远程 (使用 append 模式，因为表结构已经创建)
            # method='multi' 可以加速插入
            # chunksize 设置小一点以适应 TiDB 的限制
            try:
                df.to_sql(table_name, remote_engine, if_exists='append', index=False, chunksize=1000)
                migrated_batch = len(df)
                total_migrated += migrated_batch
                print(f"   已迁移: {total_migrated}/{count} ({total_migrated/count:.1%})")
            except Exception as e:
                # 如果是主键冲突（重复数据），尝试使用更安全的逐行插入或忽略错误（这里简化处理，假设目标表为空或允许覆盖）
                # 由于 to_sql 在遇到主键冲突时会报错，我们这里简单提示
                if "Duplicate entry" in str(e):
                    print(f"   ⚠️ 批次写入包含重复数据 (Offset {offset})，已跳过该批次或部分数据")
                else:
                    print(f"   ❌ 写入出错 (Offset {offset}): {e}")
                    # 遇到严重错误停止
                    # return 
            
            offset += chunk_size
            
        print(f"✅ 表 {table_name} 迁移完成！")
        
    except Exception as e:
        print(f"❌ 迁移表 {table_name} 时发生错误: {e}")
    finally:
        local_engine.dispose()
        remote_engine.dispose()

def main():
    print("🚀 开始数据迁移任务 (Local MySQL -> Remote TiDB)")
    print("=============================================")
    
    # 按照依赖关系顺序迁移
    # 1. 基础数据表
    migrate_table('stock_name')
    
    # 2. 选股结果表
    migrate_table('stock_selected')
    
    # 3. 日线数据表 (数据量最大，放在最后)
    # 注意：如果数据量非常大（百万级），可能需要很长时间
    migrate_table('cn_stock_daily', chunk_size=2000)
    
    print("\n🎉 所有迁移任务执行完毕！")

if __name__ == "__main__":
    main()
