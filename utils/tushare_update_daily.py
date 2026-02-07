# -*- coding: utf-8 -*-
"""
A股日线数据批量拉取与MySQL入库工具
功能说明：
1. 按日期范围拉取Tushare的A股日线数据，支持无限重试机制
2. 单日数据实时写入MySQL，内存仅保留单日数据，避免内存累积
3. 以(ts_code, trade_date)为联合主键，实现重复数据更新、新增数据插入
4. 精准统计总记录数、更新数、新增数，无负数统计异常
"""

import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ===================== 全局配置 =====================
# Tushare Pro接口初始化（优先从环境变量读取）
tushare_token = os.getenv('TUSHARE_TOKEN', '1f18885fdd078e681cf087e23c1d6f28226103f470ccf8f30fc38809')
pro = ts.pro_api(tushare_token)

# ===================== 数据库操作函数 =====================
import mysql.connector
from mysql.connector import errorcode


def write_to_mysql_with_update(df_data):
    """
    数据写入MySQL核心函数（插入/更新）
    逻辑说明：
        1. 以(ts_code, trade_date)为联合主键，存在则更新，不存在则插入
        2. 先查询已存在的主键数，精准统计更新数（避免依赖cursor.rowcount的兼容性问题）
        3. 批量写入（1000条/批），避免单次写入数据量过大导致超时

    参数：
        df_data: 待写入的单日数据DataFrame
    返回：
        tuple: (总条目数, 更新条目数)
    """
    # MySQL连接配置（优先从环境变量读取）
    config = {
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', 'showlang'),  # 数据库密码
        'host': os.getenv('DB_HOST', 'localhost'),  # 数据库地址
        'port': int(os.getenv('DB_PORT', 3306)),
        'database': os.getenv('DB_NAME', 'cn_stock'),  # 数据库名
        'charset': 'utf8mb4',  # 字符集
        'autocommit': False  # 关闭自动提交，手动控制事务
    }
    
    # TiDB Cloud SSL 配置
    if 'tidbcloud' in config['host']:
        config['ssl_ca'] = os.getenv('TIDB_CA_PATH', '/etc/ssl/cert.pem')
        config['ssl_verify_cert'] = True

    # 插入/更新SQL语句（字段与数据表cn_stock_daily严格对应）
    insert_sql = """
    INSERT INTO cn_stock_daily (
        ts_code, trade_date, price_open, price_high, price_low, price_close,
        price_pre_close, amt_chg, pct_chg, vol, amount
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        price_open = VALUES(price_open),
        price_high = VALUES(price_high),
        price_low = VALUES(price_low),
        price_close = VALUES(price_close),
        price_pre_close = VALUES(price_pre_close),
        amt_chg = VALUES(amt_chg),
        pct_chg = VALUES(pct_chg),
        vol = VALUES(vol),
        amount = VALUES(amount);
    """

    # ========== 新增：处理nan值，替换为0 ==========
    # 定义需要处理的列名（对应DataFrame中的实际列名）
    cols_to_clean = ['open', 'high', 'low', 'close', 'pre_close', 'change', 'pct_chg', 'vol', 'amount']
    # 将指定列的nan值替换为0（inplace=True直接修改原DataFrame，避免创建副本）
    df_data[cols_to_clean] = df_data[cols_to_clean].fillna(0)

    total_count = len(df_data)  # 当日待写入总条目数
    update_count = 0  # 实际更新的条目数（主键重复）
    insert_count = 0  # 实际插入的条目数（新数据）
    conn = None  # 数据库连接对象
    cursor = None  # 数据库游标对象

    try:
        # 建立数据库连接
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()

        # 将DataFrame转换为SQL批量插入的元组列表
        data_tuples = [
            (
                row['ts_code'], row['trade_date'], row['open'], row['high'], row['low'],
                row['close'], row['pre_close'], row['change'], row['pct_chg'],
                row['vol'], row['amount']
            ) for _, row in df_data.iterrows()
        ]

        # 分批执行插入/更新（每批1000条）
        batch_size = 1000
        for i in range(0, total_count, batch_size):
            batch = data_tuples[i:i + batch_size]
            batch_len = len(batch)

            # 步骤1：查询当前批次中已存在的主键数量（即需要更新的条目数）
            key_tuples = [(item[0], item[1]) for item in batch]  # 提取(ts_code, trade_date)
            placeholders = ', '.join(['(%s, %s)'] * batch_len)  # 构造IN查询占位符
            check_sql = f"""
            SELECT COUNT(*) FROM cn_stock_daily 
            WHERE (ts_code, trade_date) IN ({placeholders});
            """
            flat_keys = [k for t in key_tuples for k in t]  # 扁平化元组列表（适配SQL参数）
            cursor.execute(check_sql, flat_keys)
            batch_update_count = cursor.fetchone()[0]  # 获取当前批次更新数
            update_count += batch_update_count
            insert_count += (batch_len - batch_update_count)  # 计算当前批次插入数

            # 步骤2：执行插入/更新操作
            cursor.executemany(insert_sql, batch)

        conn.commit()  # 提交事务

        # 数据一致性校验：总条目数必须等于插入数+更新数
        assert total_count == insert_count + update_count, "统计异常：总条目数≠插入数+更新数"
        return total_count, update_count

    except mysql.connector.Error as err:
        # 异常处理：回滚事务并提示具体错误
        if conn:
            conn.rollback()
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("❌ MySQL连接失败：用户名/密码错误")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("❌ MySQL连接失败：数据库不存在")
        else:
            print(f"❌ 数据写入失败：{err}")
        return total_count, 0
    finally:
        # 资源释放：无论是否异常，都关闭游标和连接
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# ===================== 数据拉取函数 =====================
def get_single_day_data(trade_date):
    """
    拉取单日A股日线数据（带无限重试机制）
    逻辑说明：
        1. 调用Tushare pro.daily接口拉取指定日期数据
        2. 接口调用失败时，等待65秒后无限重试（直到成功或无数据）
        3. 区分交易日（有数据）和非交易日（无数据）

    参数：
        trade_date: 交易日，格式为'YYYYMMDD'
    返回：
        DataFrame: 成功返回单日数据，无数据返回空DataFrame
    """
    retry_count = 0  # 重试次数计数器

    while True:
        try:
            # 调用Tushare接口拉取数据（字段与数据表严格对应）
            df = pro.daily(
                trade_date=trade_date,
                fields=[
                    "ts_code",  # 股票代码
                    "trade_date",  # 交易日期
                    "open",  # 开盘价
                    "high",  # 最高价
                    "low",  # 最低价
                    "close",  # 收盘价
                    "pre_close",  # 前收盘价
                    "change",  # 涨跌额
                    "pct_chg",  # 涨跌幅(%)
                    "vol",  # 成交量(手)
                    "amount"  # 成交额(千元)
                ]
            )

            # 数据返回处理
            if not df.empty:
                # 格式化日期输出，提升可读性
                print(f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]} 成功，共 {len(df)} 条记录")
                return df
            else:
                print(f"没有数据（可能是非交易日） {trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}")
                return df  # 返回空DataFrame

        except Exception as e:
            # 接口调用失败，重试逻辑
            retry_count += 1
            print(f"获取 {trade_date} 数据时出错 (第{retry_count}次重试): {e}")
            print(f"等待 65 秒后重试...")
            time.sleep(65)  # 重试间隔65秒（避免触发接口频率限制）


# ===================== 主逻辑函数 =====================
def get_daily_data_by_day(start_date, end_date):
    """
    按日期范围批量拉取+写入数据（内存优化版）
    核心优化：
        1. 内存仅保留单日数据，循环结束后立即释放，避免内存累积
        2. 独立变量累加统计，不依赖最终合并的DataFrame
        3. 单日数据拉取完成后，立即写入数据库

    参数：
        start_date: 开始日期，格式为'YYYYMMDD'
        end_date: 结束日期，格式为'YYYYMMDD'
    返回：
        tuple: (是否获取到数据, 总记录数, 累计写入数, 累计更新数)
    """
    # 日期格式转换：字符串→datetime对象（便于日期遍历）
    start = datetime.strptime(start_date, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')

    # 统计变量初始化（仅保留统计值，不存储原始数据）
    total_record_count = 0  # 总记录数（所有日期有效数据条目累加）
    total_write_count = 0  # 累计写入数据库条目数
    total_update_count = 0  # 累计更新条目数（主键重复）
    has_data = False  # 标记是否获取到有效数据
    # 新增：按年统计的字典，结构 {年份: {'累计写入': 0, '累计更新': 0, '新增': 0}}
    year_stats = {}

    # 计算需要处理的总天数
    total_days = (end - start).days + 1
    print(f"共需要处理 {total_days} 天")

    # 按日期循环拉取+写入数据
    for day_count in range(total_days):
        current_date = start + timedelta(days=day_count)  # 计算当前循环日期
        trade_date = current_date.strftime('%Y%m%d')  # 转换为YYYYMMDD格式
        current_year = trade_date[:4]  # 提取当前日期的年份

        # 拉取单日数据
        df = get_single_day_data(trade_date)

        # 仅处理有数据的日期
        if not df.empty:
            has_data = True
            # 累加当日记录数到总统计
            day_record_count = len(df)
            total_record_count += day_record_count

            # 写入数据库并更新统计值
            day_total, day_updated = write_to_mysql_with_update(df)
            day_new = day_total - day_updated  # 当日新增数
            total_write_count += day_total
            total_update_count += day_updated

            # 新增：更新按年统计的数据
            if current_year not in year_stats:
                year_stats[current_year] = {'累计写入': 0, '累计更新': 0, '新增': 0}
            year_stats[current_year]['累计写入'] += day_total
            year_stats[current_year]['累计更新'] += day_updated
            year_stats[current_year]['新增'] += day_new

            # 输出当日写入结果（格式化输出，提升可读性）
            print(
                f"           ✅ 写入完成：当日总条目 {day_record_count} 条，更新 {day_updated} 条，新增 {day_total - day_updated} 条")

            # 显式清空当日DataFrame，释放内存（Python自动回收，显式更清晰）
            df = None

    # 返回统计结果（无合并DataFrame，降低内存占用）
    return has_data, total_record_count, total_write_count, total_update_count, year_stats


# ===================== 程序入口 =====================
if __name__ == "__main__":
    # 基础配置：获取当前日期作为默认值
    today = datetime.now().strftime('%Y%m%d')

    # 用户输入：日期范围（支持默认值，直接回车使用当天）
    # 在 Streamlit 中调用时，通常通过 stdin 传递参数
    try:
        import sys
        if len(sys.stdin.read(0)): # Check if stdin has data
             lines = sys.stdin.readlines()
             if len(lines) >= 2:
                 start_date = lines[0].strip()
                 end_date = lines[1].strip()
             else:
                 start_date = today
                 end_date = today
        else:
             start_date = today
             end_date = today
    except:
        start_date = today
        end_date = today

    # 输出任务信息
    print(f"开始按天获取数据，日期范围: {start_date} 到 {end_date}")
    print("=" * 50)

    # 执行主逻辑：拉取+写入数据
    has_data, total_record, total_write, total_update, year_stats = get_daily_data_by_day(start_date, end_date)

    # 新增：按年展示数据条目统计（标题和数值严格右对齐）
    if has_data:
        print("\n📈 按年数据条目统计：")
        print("-" * 60)
        # 核心修改：统一列宽度，标题和数值都右对齐，宽度设为18（适配千分位数字长度）
        col_width = 14
        print(f"{'年份':<10} {'累计写入':>{col_width}} {'累计更新':>{col_width}} {'新增':>{col_width}}")
        print("-" * 60)
        # 遍历年份，格式化输出：千分位 + 固定宽度右对齐
        for year in sorted(year_stats.keys()):
            stats = year_stats[year]
            # 格式化数字为千分位，并填充到固定宽度，确保和标题右对齐
            write_count = f"{stats['累计写入']:,}".rjust(col_width)
            update_count = f"{stats['累计更新']:,}".rjust(col_width)
            new_count = f"{stats['新增']:,}".rjust(col_width)
            print(f"{year:<10}{write_count}{update_count}{new_count}")
        print("-" * 60)

    # 输出最终统计结果
    if has_data:
        print("=" * 50)
        print("数据获取完成!")
        print(f"总记录数: {total_record:,}")
        print(
            f"📊 数据库写入汇总：累计写入 {total_write:,} 条，累计更新 {total_update:,} 条，新增 {total_write - total_update:,} 条")
    else:
        print("没有获取到任何数据")
