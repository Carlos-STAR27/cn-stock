# -*- coding: utf-8 -*-
"""
股票选股分析程序
====================
功能说明：
1. 从MySQL数据库读取指定日期区间的股票日线数据
2. 根据通达信公式筛选符合条件的股票
3. 处理日期格式（节假日/工作日调整、YYYYMMDD格式转换）
4. 清理临时字段，调整结果表字段顺序
5. 将选股结果写入MySQL数据库

使用依赖：
- pandas: 数据处理
- pymysql/sqlalchemy: MySQL数据库交互
- chinese_calendar: 节假日/工作日判断
- Python 3.7+

配置说明：
- 修改mysql_config字典中的数据库连接信息
- 可调整选股参数d1（默认值0）
====================
作者：自动生成
更新时间：2026-01-26
"""

import pandas as pd
import pymysql
from sqlalchemy import create_engine
from datetime import datetime, timedelta
# 导入节假日判断库，用于工作日/节假日识别
from chinese_calendar import is_holiday, is_workday
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ========================== 数据库配置区 ==========================
# 数据库连接配置（优先从环境变量读取）
mysql_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'showlang'),
    'database': os.getenv('DB_NAME', 'cn_stock'),
    'ssl_ca': os.getenv('TIDB_CA_PATH', '/etc/ssl/cert.pem') if 'tidbcloud' in os.getenv('DB_HOST', '') else None
}

# 创建SQLAlchemy数据库连接引擎
connect_args = {}
if mysql_config['ssl_ca']:
    connect_args['ssl'] = {'ca': mysql_config['ssl_ca'], 'check_hostname': False}

engine = create_engine(
    f"mysql+pymysql://{mysql_config['user']}:{mysql_config['password']}@"
    f"{mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}",
    connect_args=connect_args,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True  # 检查连接有效性
)


# ========================== 数据读取模块 ==========================
def load_stock_data(start_date='20200101', end_date='20251231'):
    """
    从MySQL的cn_stock_daily表读取指定日期区间的股票日线数据

    参数说明：
    ----------
    start_date : str, 可选
        数据起始日期，格式为YYYYMMDD，默认值'20200101'
    end_date : str, 可选
        数据结束日期，格式为YYYYMMDD，默认值'20251231'

    返回值：
    ----------
    pandas.DataFrame
        包含股票日线数据的DataFrame，字段说明：
        - ts_code: 股票代码
        - trade_date: 交易日期（datetime类型）
        - price_open/price_high/price_low/price_close: 开/高/低/收盘价
        - price_pre_close: 前收盘价
        - amt_chg: 涨跌额
        - pct_chg: 涨跌幅（%）
        - vol: 成交量（手）
        - amount: 成交金额（元）
    """
    # 构造SQL查询语句，读取指定字段和日期区间的数据
    sql = f"""
    SELECT ts_code, trade_date, price_open, price_high, price_low, 
           price_close, price_pre_close, amt_chg, pct_chg, vol, amount
    FROM cn_stock_daily
    WHERE trade_date BETWEEN '{start_date}' AND '{end_date}'
    ORDER BY ts_code, trade_date
    """
    # 执行SQL查询并读取数据
    df = pd.read_sql(sql, engine)
    # 将trade_date字段从字符串转换为datetime类型（便于后续日期计算）
    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    return df


# ========================== 日期处理辅助函数 ==========================
def get_nearest_workday_forward(date):
    """
    日期向后顺延：获取输入日期之后最近的工作日（跳过周末和法定节假日）

    参数说明：
    ----------
    date : datetime.datetime
        输入的基准日期（datetime类型）

    返回值：
    ----------
    datetime.datetime
        顺延之后的最近工作日（datetime类型，时分秒为00:00:00）

    应用场景：
    ----------
    用于计算buy_date字段
    """
    # 提取date对象的date部分（去除时分秒），适配chinese_calendar库的参数要求
    check_date = date.date()

    # 循环判断，直到找到工作日
    while True:
        # 判断当前日期是否为工作日（非周末+非法定节假日）
        if is_workday(check_date):
            break
        # 非工作日则向后顺延1天
        check_date += timedelta(days=1)

    # 将date对象转换回datetime对象（时分秒设为0）并返回
    return datetime.combine(check_date, datetime.min.time())


def get_nearest_workday_backward(date):
    """
    日期向前回溯：获取输入日期之前最近的工作日（跳过周末和法定节假日）

    参数说明：
    ----------
    date : datetime.datetime
        输入的基准日期（datetime类型）

    返回值：
    ----------
    datetime.datetime
        回溯之后的最近工作日（datetime类型，时分秒为00:00:00）

    应用场景：
    ----------
    用于计算gold_date字段
    """
    # 提取date对象的date部分（去除时分秒），适配chinese_calendar库的参数要求
    check_date = date.date()

    # 循环判断，直到找到工作日
    while True:
        # 判断当前日期是否为工作日（非周末+非法定节假日）
        if is_workday(check_date):
            break
        # 非工作日则向前回溯1天
        check_date -= timedelta(days=1)

    # 将date对象转换回datetime对象（时分秒设为0）并返回
    return datetime.combine(check_date, datetime.min.time())


def minus_n_workdays(date, n):
    """
    日期向前推N个工作日：从指定日期向前数N个有效工作日（跳过周末和节假日）

    参数说明：
    ----------
    date : datetime.datetime
        输入的基准日期（datetime类型）
    n : int
        要向前推的工作日数量

    返回值：
    ----------
    datetime.datetime
        向前推N个工作日后的日期（datetime类型，时分秒为00:00:00）

    应用场景：
    ----------
    用于计算gold_date的基准日期（buy_date向前推4个工作日）
    """
    # 提取date对象的date部分（去除时分秒）
    current_date = date.date()
    # 计数器：已找到的工作日数量
    count = 0

    # 循环向前找，直到凑够N个工作日
    while count < n:
        # 日期向前推1天
        current_date -= timedelta(days=1)
        # 如果是工作日，计数器+1
        if is_workday(current_date):
            count += 1

    # 将date对象转换回datetime对象（时分秒设为0）并返回
    return datetime.combine(current_date, datetime.min.time())


# ========================== 核心选股逻辑模块 ==========================
def select_stocks(df, d1=0):
    """
    核心选股逻辑：基于通达信公式筛选符合条件的股票

    参数说明：
    ----------
    df : pandas.DataFrame
        输入的股票日线数据（来自load_stock_data函数的返回值）
    d1 : int, 可选
        选股公式中的D1参数，用于调整滞后值计算，默认值0

    返回值：
    ----------
    pandas.DataFrame
        符合选股条件的股票数据，包含新增字段：
        - buy_date: 买入日期（datetime类型）
        - gold_date: 黄金日期（datetime类型）
        已移除所有ref_开头的临时计算字段

    选股条件（需同时满足）：
    ----------
    1. 当日涨幅8%以上：REF(CLOSE,D1+3)/REF(CLOSE,D1+4) > 1.08
    2. 成交量逐日递减：REF(VOL,D1+0)*1.1 < REF(VOL,D1+3)
                       AND REF(VOL,D1+1)*1.1 < REF(VOL,D1+2)
                       AND REF(VOL,D1+2)*1.1 < REF(VOL,D1+3)
    3. 三天前放量：REF(VOL,D1+3) >= 1.5 * REF(VOL,D1+4)
    4. 最低价递增：REF(LOW,D1+0) > (REF(LOW,D1+3)+REF(CLOSE,D1+3))/2
                   AND REF(LOW,D1+1) > (REF(LOW,D1+3)+REF(CLOSE,D1+3))/2
                   AND REF(LOW,D1+2) > (REF(LOW,D1+3)+REF(CLOSE,D1+3))/2
    """
    # 存储每个股票符合条件的记录
    result_list = []

    # 按股票代码分组，逐只股票处理
    for ts_code, group in df.groupby('ts_code'):
        # 按交易日期升序排列，并重置索引（避免分组后索引混乱）
        group = group.sort_values('trade_date').reset_index(drop=True)

        # ===================== 计算滞后值（通达信REF函数） =====================
        # REF(X,N) 表示取N天前的X值，这里基于D1参数调整滞后天数
        group['ref_close_d1_3'] = group['price_close'].shift(d1 + 3)  # REF(CLOSE,D1+3)
        group['ref_close_d1_4'] = group['price_close'].shift(d1 + 4)  # REF(CLOSE,D1+4)
        group['ref_vol_d1_0'] = group['vol'].shift(d1 + 0)  # REF(VOL,D1+0)
        group['ref_vol_d1_1'] = group['vol'].shift(d1 + 1)  # REF(VOL,D1+1)
        group['ref_vol_d1_2'] = group['vol'].shift(d1 + 2)  # REF(VOL,D1+2)
        group['ref_vol_d1_3'] = group['vol'].shift(d1 + 3)  # REF(VOL,D1+3)
        group['ref_vol_d1_4'] = group['vol'].shift(d1 + 4)  # REF(VOL,D1+4)
        group['ref_low_d1_0'] = group['price_low'].shift(d1 + 0)  # REF(LOW,D1+0)
        group['ref_low_d1_1'] = group['price_low'].shift(d1 + 1)  # REF(LOW,D1+1)
        group['ref_low_d1_2'] = group['price_low'].shift(d1 + 2)  # REF(LOW,D1+2)
        group['ref_low_d1_3'] = group['price_low'].shift(d1 + 3)  # REF(LOW,D1+3)

        # ===================== 计算buy_date和gold_date =====================
        # 1. 计算原始buy_date并调整为最近的工作日
        raw_buy_date = group['trade_date'] - timedelta(days=d1 - 1)
        group['buy_date'] = raw_buy_date.apply(lambda x: get_nearest_workday_forward(x))

        # 2. 基于buy_date向前推4个工作日，再调整为最近的工作日（得到gold_date）
        raw_gold_date = group['buy_date'].apply(lambda x: minus_n_workdays(x, 4))
        group['gold_date'] = raw_gold_date.apply(lambda x: get_nearest_workday_backward(x))

        # ===================== 选股条件判断 =====================
        # 条件1：当日涨幅8%以上
        condition1 = (group['ref_close_d1_3'] / group['ref_close_d1_4']) > 1.08

        # 条件2：成交量逐日递减（三个子条件需同时满足）
        condition2 = (group['ref_vol_d1_0'] * 1.1 < group['ref_vol_d1_3']) & \
                     (group['ref_vol_d1_1'] * 1.1 < group['ref_vol_d1_2']) & \
                     (group['ref_vol_d1_2'] * 1.1 < group['ref_vol_d1_3'])

        # 条件3：三天前放量
        condition3 = group['ref_vol_d1_3'] >= 1.5 * group['ref_vol_d1_4']

        # 条件4：最低价递增（三个子条件需同时满足）
        avg_price = (group['ref_low_d1_3'] + group['ref_close_d1_3']) / 2
        condition4 = (group['ref_low_d1_0'] > avg_price) & \
                     (group['ref_low_d1_1'] > avg_price) & \
                     (group['ref_low_d1_2'] > avg_price)

        # 综合所有条件：需同时满足条件1-4
        final_condition = condition1 & condition2 & condition3 & condition4

        # 筛选出符合条件的记录
        selected = group[final_condition]
        # 如果当前股票无符合条件的记录，跳过
        if selected.empty:
            continue

        # 清理临时计算字段：移除所有ref_开头的字段
        ref_cols = [col for col in selected.columns if col.startswith('ref_')]
        selected = selected.drop(columns=ref_cols)
        # 将当前股票符合条件的记录加入结果列表
        result_list.append(selected)

    # 合并所有股票的符合条件记录
    if result_list:
        Stock_Selected = pd.concat(result_list, ignore_index=True)
    else:
        # 无符合条件的记录时，返回空DataFrame
        Stock_Selected = pd.DataFrame()

    return Stock_Selected


# ========================== 主程序执行入口 ==========================
if __name__ == "__main__":
    # ===================== 初始化日期参数 =====================
    # 获取当前时间，用于计算默认的起始/结束日期
    today = datetime.now()
    # 默认起始日期：当前日期向前推4天（格式YYYYMMDD）
    default_start_date = (today - timedelta(days=4)).strftime('%Y%m%d')
    # 默认结束日期：当前日期（格式YYYYMMDD）
    default_end_date = today.strftime('%Y%m%d')

    # 接收用户输入的起始/结束日期（为空则使用默认值）
    # 在 Streamlit 中调用时，通常通过 stdin 传递参数，或者修改为函数调用
    try:
        import sys
        if len(sys.stdin.read(0)): # Check if stdin has data
             lines = sys.stdin.readlines()
             if len(lines) >= 2:
                 start_date = lines[0].strip()
                 end_date = lines[1].strip()
             else:
                 start_date = default_start_date
                 end_date = default_end_date
        else:
             start_date = default_start_date
             end_date = default_end_date
    except:
        start_date = default_start_date
        end_date = default_end_date

    # ===================== 数据加载与选股 =====================
    # 加载指定日期区间的股票日线数据
    print(f"\n📥 正在读取 {start_date} 至 {end_date} 的股票日线数据...")
    stock_df = load_stock_data(start_date=start_date, end_date=end_date)

    # 执行核心选股逻辑
    print("🔍 正在执行选股逻辑...")
    Stock_Selected = select_stocks(stock_df, d1=0)

    # ===================== 结果数据处理 =====================
    # 清理所有ref_开头的临时字段（双重保障）
    ref_columns = [col for col in Stock_Selected.columns if col.startswith('ref_')]
    if ref_columns:
        Stock_Selected = Stock_Selected.drop(columns=ref_columns)

    # 添加程序执行时间字段
    # 获取当前时间（程序执行结束时间）
    execute_end_time = datetime.now()
    # 执行日期（格式：YYYY-MM-DD）
    Stock_Selected['execute_date'] = execute_end_time.strftime('%Y-%m-%d')
    # 执行时间（格式：HH:MM:SS）
    Stock_Selected['execute_time'] = execute_end_time.strftime('%H:%M:%S')

    # 调整字段顺序：将execute_date和execute_time放到最前面
    if not Stock_Selected.empty:
        cols = Stock_Selected.columns.tolist()
        cols.remove('execute_date')
        cols.remove('execute_time')
        new_cols = ['execute_date', 'execute_time'] + cols
        Stock_Selected = Stock_Selected[new_cols]

        # 日期格式转换：将trade_date/buy_date/gold_date转为YYYYMMDD字符串格式
        Stock_Selected['trade_date'] = Stock_Selected['trade_date'].dt.strftime('%Y%m%d')
        Stock_Selected['buy_date'] = Stock_Selected['buy_date'].dt.strftime('%Y%m%d')
        Stock_Selected['gold_date'] = Stock_Selected['gold_date'].dt.strftime('%Y%m%d')

    # ===================== 结果输出与数据库写入 =====================
    print("\n📊 ===== 选股结果 ======")
    if not Stock_Selected.empty:
        # 输出选股结果统计信息
        print(f"✅ 共筛选出 {len(Stock_Selected)} 条符合条件的股票记录")
        # 展示核心字段的结果（便于快速查看）
        print("\n核心结果预览：")
        print(Stock_Selected[['execute_date', 'execute_time', 'ts_code', 'trade_date',
                              'gold_date', 'buy_date', 'price_close', 'vol', 'price_low']])

        # 将结果写入MySQL数据库（基于4个联合主键实现存在更新、不存在插入）
        print("\n📤 开始写入MySQL数据库...")
        try:
            # 1. 先创建数据库连接游标
            conn = engine.raw_connection()
            cursor = conn.cursor()

            # 2. 遍历每条数据，执行INSERT ... ON DUPLICATE KEY UPDATE逻辑
            # 提取字段列表（排除索引）
            columns = Stock_Selected.columns.tolist()
            # 构建字段字符串
            cols_str = ', '.join(columns)
            # 构建占位符字符串
            placeholders = ', '.join(['%s'] * len(columns))
            # 构建更新字符串（主键字段不更新，其他字段更新）
            update_str = ', '.join([
                f"{col} = VALUES({col})"
                for col in columns
                if col not in ['execute_date', 'execute_time', 'ts_code', 'trade_date']
            ])

            # 3. 批量处理数据
            batch_size = 1000
            total_rows = len(Stock_Selected)
            inserted_count = 0
            updated_count = 0

            for i in range(0, total_rows, batch_size):
                # 截取批次数据
                batch_data = Stock_Selected.iloc[i:i + batch_size]
                # 转换为元组列表
                values = [tuple(row) for row in batch_data.values]

                # 构建批量插入SQL语句（MySQL特有ON DUPLICATE KEY UPDATE）
                sql = f"""
                INSERT INTO stock_selected ({cols_str}) 
                VALUES ({placeholders}) 
                ON DUPLICATE KEY UPDATE {update_str}
                """

                # 执行批量插入/更新
                cursor.executemany(sql, values)
                # 统计插入/更新行数
                rowcount = cursor.rowcount
                inserted_count += rowcount - updated_count  # 新增行数
                updated_count += rowcount // 2  # 更新行数（MySQL中更新时rowcount返回2）

            # 4. 提交事务
            conn.commit()
            print(f"✅ 数据库写入完成！新增 {inserted_count} 条，更新 {updated_count} 条")

            # 5. 关闭游标和连接
            cursor.close()
            conn.close()

        except Exception as e:
            print(f"❌ 数据库写入失败：{str(e)}")
            # 出错时回滚事务
            if 'conn' in locals() and conn.open:
                conn.rollback()

        # 可选：将结果保存到Excel文件
        # Stock_Selected.to_excel('选股结果.xlsx', index=False)
        # print("📄 结果已保存到选股结果.xlsx文件")
    else:
        # 无符合条件的记录时的提示
        print("❌ 未找到符合条件的股票，无需写入数据库")

    # ===================== 资源释放 =====================
    # 关闭数据库连接引擎，释放资源
    engine.dispose()
    print("\n🔚 程序执行完成，数据库连接已关闭")
