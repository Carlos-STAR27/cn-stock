# -*- coding: utf-8 -*-
"""
从 Baostock 更新股票名称到数据库
"""
import baostock as bs
import pandas as pd
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import text
from dotenv import load_dotenv

# 添加当前目录到系统路径，以便导入 db_utils
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from db_utils import get_db_engine, log_task_execution
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(current_dir)))
    from utils.db_utils import get_db_engine, log_task_execution

load_dotenv()
load_dotenv('.env.local')

def update_stock_names():
    print("🚀 开始从 Baostock 更新股票名称...")
    
    try:
        log_task_execution("股票名称抽取", "RUNNING", "开始执行")
        
        # 1. 登录 Baostock
        lg = bs.login()
        if lg.error_code != '0':
            error_msg = f"Baostock 登录失败: {lg.error_msg}"
            print(error_msg)
            log_task_execution("股票名称抽取", "FAIL", error_msg)
            return

        # 2. 获取所有股票
        print("正在获取股票列表...")
        today_str = datetime.now().strftime('%Y-%m-%d')
        rs = bs.query_all_stock(day=today_str)
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
            
        # 如果今天没数据（可能是周末/节假日），尝试回退几天
        if not data_list:
            print(f"日期 {today_str} 无数据，尝试回退...")
            for i in range(1, 10): # 增加回退天数以防长假
                prev_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                print(f"尝试获取 {prev_date} 数据...")
                rs = bs.query_all_stock(day=prev_date)
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                if data_list:
                    print(f"成功获取 {prev_date} 数据")
                    break
            
        if not data_list:
            error_msg = "未获取到股票数据"
            print(error_msg)
            bs.logout()
            log_task_execution("股票名称抽取", "FAIL", error_msg)
            return

        df = pd.DataFrame(data_list, columns=rs.fields)
        
        # 3. 数据清洗
        # 筛选出股票 (type=1) 且状态为上市 (status=1)
        # 注意：Baostock 字段: code, tradeStatus, code_name
        # 但 query_all_stock 返回字段通常是 code, tradeStatus, code_name
        # 具体字段名需要确认，通常是 code, tradeStatus, code_name
        
        # 简单清洗：只保留 code 和 code_name
        # 转换 code 格式：sh.600000 -> 600000.SH
        def convert_code(code):
            if code.startswith('sh.'):
                return code[3:] + '.SH'
            elif code.startswith('sz.'):
                return code[3:] + '.SZ'
            elif code.startswith('bj.'):
                return code[3:] + '.BJ'
            return code

        df['ts_code'] = df['code'].apply(convert_code)
        df['ts_code_name'] = df['code_name']
        
        # 只要这两个字段
        df_save = df[['ts_code', 'ts_code_name']]
        
        # 4. 存入数据库
        print(f"准备写入 {len(df_save)} 条数据...")
        engine = get_db_engine()
        with engine.connect() as conn:
            # 创建表 (如果不存在)
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_name (
                ts_code VARCHAR(20) PRIMARY KEY,
                ts_code_name VARCHAR(50)
            )
            """))
            # 清空表 (全量更新)
            conn.execute(text("TRUNCATE TABLE stock_name"))
            conn.commit()
            
        # 写入新数据
        df_save.to_sql('stock_name', engine, if_exists='append', index=False, chunksize=1000)
        
        bs.logout()
        engine.dispose()
        
        success_msg = f"成功更新 {len(df_save)} 条股票名称数据"
        print(success_msg)
        log_task_execution("股票名称抽取", "SUCCESS", success_msg)
        
    except Exception as e:
        error_msg = f"执行出错: {str(e)}"
        print(error_msg)
        try:
            bs.logout()
        except:
            pass
        log_task_execution("股票名称抽取", "FAIL", error_msg)

if __name__ == "__main__":
    update_stock_names()
