import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
import subprocess
import sys
from utils.db_utils import get_config, get_db_engine  # 复用 db_utils 中的逻辑

# 加载环境变量
load_dotenv()
load_dotenv('.env.local')

# --- 数据库连接 (带缓存) ---
@st.cache_resource
def get_engine():
    """获取全局数据库连接引擎 (带缓存)"""
    return get_db_engine()

# 初始化 engine
try:
    engine = get_engine()
except Exception as e:
    st.error(f"数据库连接失败: {e}")
    engine = None

# 字段中文别名映射
COLUMN_DISPLAY_MAP = {
    "execute_date": "选股日期",
    "execute_time": "选股时间",
    "ts_code": "股票代码",
    "stock_name": "股票名称",
    "trade_date": "开盘日",
    "price_open": "开盘价",
    "price_close": "收盘价",
    "price_high": "最高价",
    "price_low": "最低价",
    "vol": "量",
    "amount": "金额",
    "buy_date": "建议买入日期",
    "gold_date": "AI 观察日"
}

# 页面配置
st.set_page_config(
    page_title="Quantum Stock | 智能选股",
    page_icon="static/quantum_stock_icon.svg",
    layout="wide",
)

# --- 登录验证逻辑 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_login():
    expected_username = get_config("APP_USERNAME", "admin")
    expected_password = get_config("APP_PASSWORD", "admin")
    
    if st.session_state.username_input == expected_username and st.session_state.password_input == expected_password:
        st.session_state.authenticated = True
    else:
        st.error("用户名或密码错误")

if not st.session_state.authenticated:
    # 简单的登录页面样式
    st.markdown("""
    <style>
        div[data-testid="stForm"] {
            max-width: 400px;
            margin: 0 auto;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            background-color: white;
        }
        .stApp {
            background-color: #F5F5F7;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("<h1 style='text-align: center; color: #1D1D1F; margin-bottom: 30px;'>Quantum Stock Login</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.text_input("用户名", key="username_input")
            st.text_input("密码", type="password", key="password_input")
            st.form_submit_button("登录", type="primary", on_click=check_login, use_container_width=True)
    
    st.stop()

# --- 登录成功后显示退出按钮 ---
st.sidebar.button("退出登录", on_click=lambda: st.session_state.update(authenticated=False))

logo_path = "static/quantum_stock_icon.svg"
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image(logo_path, width=80)
with col_title:
    # 使用 Markdown 自定义标题样式 (银色/浅灰色)
    st.markdown('<h1 style="color: #C0C0C0;">QUANTUM STOCK | 智能选股系统</h1>', unsafe_allow_html=True)

# --- CSS 美化 (Apple Developer 风格) ---
st.markdown("""
<style>
    /* 全局字体与配色 */
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #1D1D1F;
    }
    
    /* 统一输入框宽度 (约20字符) */
    div[data-testid="stTextInput"], 
    div[data-testid="stDateInput"], 
    div[data-testid="stSelectbox"],
    div[data-testid="stNumberInput"] {
        max-width: 220px !important;
        width: 220px !important;
    }
    
    /* 按钮样式 (Apple Blue) */
    div.stButton > button {
        border-radius: 6px;
        font-weight: 500;
        border: none;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        transition: background-color 0.2s;
    }
    div.stButton > button[kind="primary"] {
        background-color: #007AFF; 
        color: white;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #0051A8;
    }
    div.stButton > button[kind="secondary"] {
        background-color: #F5F5F7;
        color: #1D1D1F;
    }
    
    /* Tab 样式微调 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 16px;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 14px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# --- 侧边栏：系统状态 ---
st.sidebar.header("系统状态")

# 检查连接状态
if engine:
    try:
        with engine.connect() as conn:
            pass
        st.sidebar.success("✅ 数据库已连接")
        
        # 显示连接信息 (Masked)
        db_host = get_config("DB_HOST", "Unknown")
        st.sidebar.caption(f"Host: {db_host[:15]}...")
    except Exception as e:
        st.sidebar.error("❌ 数据库连接异常")
        st.sidebar.caption(f"Error: {str(e)[:50]}...")
else:
    st.sidebar.error("❌ 数据库未连接")
    st.sidebar.info("请检查 .env 文件或 Secrets 配置")
    
    # 调试信息 (仅在连接失败时显示关键配置状态)
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 调试信息")
    
    # 检查关键配置是否存在 (不显示具体值)
    config_keys = ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    for key in config_keys:
        val = get_config(key)
        status = "✅ Configured" if val else "❌ Missing"
        st.sidebar.text(f"{key}: {status}")
        
    # 打印尝试连接的 Host (Masked)
    host_val = get_config("DB_HOST")
    if host_val:
        st.sidebar.text(f"Target Host: {host_val[:10]}***")

# --- 辅助函数：读取任务日志 ---
def get_task_logs(task_name, limit=20):
    """读取指定任务的最近日志"""
    if not engine:
        return pd.DataFrame()
    
    try:
        query = text("""
        SELECT execute_time, status, message 
        FROM task_logs 
        WHERE task_name = :task_name 
        ORDER BY execute_time DESC 
        LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query, {"task_name": task_name, "limit": limit})
            return pd.DataFrame(result.fetchall(), columns=["执行时间", "状态", "详情"])
    except Exception as e:
        st.error(f"读取日志失败: {e}")
        return pd.DataFrame()


# --- 辅助函数：运行外部脚本 ---
def run_script(script_path, inputs):
    """
    运行外部 Python 脚本并流式输出结果
    :param script_path: 脚本绝对路径
    :param inputs: 输入列表，将按顺序发送给脚本的 input()
    """
    if not os.path.exists(script_path):
        st.error(f"找不到脚本文件: {script_path}")
        return

    cmd = [sys.executable, script_path]
    
    # 准备输入数据
    input_str = "\n".join(inputs) + "\n"
    
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # 写入输入
        try:
            process.stdin.write(input_str)
            process.stdin.flush()
            process.stdin.close()
        except Exception as e:
            st.error(f"写入输入失败: {e}")

        # 显示输出容器
        output_container = st.empty()
        full_output = ""
        
        # 读取输出
        while True:
            output_line = process.stdout.readline()
            error_line = process.stderr.readline()
            
            if output_line == '' and error_line == '' and process.poll() is not None:
                break
                
            if output_line:
                full_output += output_line
                # 实时刷新显示（仅显示最后 20 行以避免过长，或者显示完整日志）
                output_container.code(full_output, language="bash")
                
            if error_line:
                full_output += f"ERROR: {error_line}"
                output_container.code(full_output, language="bash")
                
        return_code = process.poll()
        if return_code == 0:
            st.success("脚本执行完成！")
        else:
            st.error(f"脚本执行出错，退出码: {return_code}")
            
    except Exception as e:
        st.error(f"运行脚本时发生错误: {e}")

# --- 主功能区 ---

if not engine:
    st.info("数据库连接初始化失败，请检查配置。")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 选股池查询", "⚡ 执行选股", "📈 日K线抽取", "💾 选股池管理", "📥 股票名称抽取"])

# --- Tab 1: 数据查询 ---
with tab1:
    # 布局：6个条件 + 1个按钮 + 占位符 (靠左对齐)
    # 间隔说明：输入框之间约3字符(0.3)，按钮前约5字符(0.5)
    c1, _, c2, _, c3, _, c4, _, c5, _, c6, _, c7, c8 = st.columns([1.2, 0.3, 1.2, 0.3, 1.2, 0.3, 1.2, 0.3, 1.2, 0.3, 1.2, 0.5, 0.8, 0.5], vertical_alignment="bottom")
    
    with c1:
        search_start_date = st.date_input("建议买入日期 (Start)", value=None)
    with c2:
        search_end_date = st.date_input("建议买入日期 (End)", value=None)
    with c3:
        gold_start_date = st.date_input("AI 观察日 (Start)", value=None)
    with c4:
        gold_end_date = st.date_input("AI 观察日 (End)", value=None)
    with c5:
        # 动态获取选股日期列表
        query_dates_list = []
        try:
            if connection_success:
                 with engine.connect() as conn:
                    df_q_dates = pd.read_sql("SELECT DISTINCT execute_date FROM stock_selected ORDER BY execute_date DESC", conn)
                    if not df_q_dates.empty:
                        query_dates_list = df_q_dates['execute_date'].astype(str).tolist()
        except Exception:
            pass
            
        search_execute_date = st.selectbox(
            "选股日期", 
            options=query_dates_list, 
            index=None, 
            placeholder="请选择"
        )
    with c6:
        search_ts_code = st.text_input("股票代码", placeholder="例如: 000001.SZ")
    with c7:
        run_query = st.button("查询", type="primary")
        
    if run_query:
        st.session_state.query_active = True
        st.session_state.query_page = 1
        st.session_state.query_params = {
            "search_ts_code": search_ts_code,
            "search_start_date": search_start_date,
            "search_end_date": search_end_date,
            "gold_start_date": gold_start_date,
            "gold_end_date": gold_end_date,
            "search_execute_date": search_execute_date
        }

    if st.session_state.get("query_active", False):
        params = st.session_state.query_params
        
        # 基础查询条件
        base_where = " WHERE 1=1"
        sql_params = {}
        
        if params["search_ts_code"]:
            base_where += " AND t1.ts_code LIKE :ts_code"
            sql_params['ts_code'] = f"%{params['search_ts_code']}%"
        
        if params["search_start_date"]:
            base_where += " AND t1.buy_date >= :start_date"
            sql_params['start_date'] = params["search_start_date"].strftime('%Y%m%d')
        if params["search_end_date"]:
            base_where += " AND t1.buy_date <= :end_date"
            sql_params['end_date'] = params["search_end_date"].strftime('%Y%m%d')

        if params["gold_start_date"]:
            base_where += " AND t1.gold_date >= :gold_start"
            sql_params['gold_start'] = params["gold_start_date"].strftime('%Y%m%d')
        if params["gold_end_date"]:
            base_where += " AND t1.gold_date <= :gold_end"
            sql_params['gold_end'] = params["gold_end_date"].strftime('%Y%m%d')

        if params.get("search_execute_date"):
            base_where += " AND t1.execute_date = :execute_date"
            sql_params['execute_date'] = params["search_execute_date"]

        # 分页参数
        page_size = 50
        current_page = st.session_state.get("query_page", 1)
        offset = (current_page - 1) * page_size
        
        try:
            with engine.connect() as conn:
                # 1. 查询总条数
                count_query = text(f"SELECT COUNT(*) FROM stock_selected t1 {base_where}")
                total_count = conn.execute(count_query, sql_params).scalar()
                
                # 2. 查询当前页数据
                data_query = text(f"""
                    SELECT 
                        t1.buy_date, t1.gold_date, t1.execute_date, t1.execute_time, 
                        t1.ts_code, t2.ts_code_name as stock_name,
                        t1.trade_date, t1.price_open, t1.price_close, t1.price_high, t1.price_low,
                        t1.vol, t1.amount
                    FROM stock_selected t1
                    LEFT JOIN stock_name t2 ON t1.ts_code = t2.ts_code
                    {base_where}
                    ORDER BY t1.trade_date DESC 
                    LIMIT :limit OFFSET :offset
                """)
                # 合并分页参数
                query_params = sql_params.copy()
                query_params.update({"limit": page_size, "offset": offset})
                
                df = pd.read_sql(data_query, conn, params=query_params)
            
            # 数据处理与展示
            if not df.empty:
                # 格式化日期
                date_cols = ['trade_date', 'buy_date', 'gold_date']
                for col in date_cols:
                    if col in df.columns:
                        df[col] = df[col].astype(str).apply(
                            lambda x: f"{x[:4]}-{x[4:6]}-{x[6:]}" if len(x) == 8 and x.isdigit() else x
                        )
                
                # 链接处理
                def make_sina_link(code):
                    if not isinstance(code, str) or "." not in code:
                        return code
                    try:
                        symbol, suffix = code.split('.')
                        market = suffix.lower()
                        sina_code = f"{market}{symbol}"
                        url = f"https://finance.sina.com.cn/realstock/company/{sina_code}/nc.shtml?display_code={code}"
                        return url
                    except:
                        return code

                if 'ts_code' in df.columns:
                    df['ts_code'] = df['ts_code'].apply(make_sina_link)

            df_display = df.rename(columns=COLUMN_DISPLAY_MAP)
            
            # 调整列顺序
            cols = list(df_display.columns)
            if "股票代码" in cols and "股票名称" in cols:
                cols.remove("股票名称")
                idx = cols.index("股票代码")
                cols.insert(idx + 1, "股票名称")
                df_display = df_display[cols]
                
            st.dataframe(
                df_display, 
                width="stretch",
                column_config={
                    "股票代码": st.column_config.LinkColumn(
                        "股票代码",
                        display_text=r"display_code=(.*)",
                    ),
                    "股票名称": st.column_config.TextColumn(
                        "股票名称",
                        width="medium",
                    ),
                    "量": st.column_config.NumberColumn(
                        "量",
                        format="%d",
                        step=1,
                    ),
                    "金额": st.column_config.NumberColumn(
                        "金额",
                        format="%.2f",
                        step=0.01,
                    )
                }
            )
            
            # 分页控件
            total_pages = (total_count + page_size - 1) // page_size
            if total_pages > 0:
                col_prev, col_info, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if current_page > 1:
                        if st.button("上一页", key="prev_page"):
                            st.session_state.query_page -= 1
                            st.rerun()
                
                with col_info:
                    st.markdown(f"<div style='text-align: center; line-height: 2.5;'>第 {current_page} / {total_pages} 页 (共 {total_count} 条)</div>", unsafe_allow_html=True)
                
                with col_next:
                    if current_page < total_pages:
                        if st.button("下一页", key="next_page"):
                            st.session_state.query_page += 1
                            st.rerun()
            else:
                st.info("未查询到数据")

        except Exception as e:
            st.error(f"查询出错: {e}")

# --- Tab 2: 新增数据 (选股) ---
with tab2:
    script_path_select = os.path.join(os.path.dirname(__file__), "utils", "tushare_select_stock.py")
    
    with st.form("select_stock_form"):
        # 布局：2个条件 + 1个按钮 + 占位符 (靠左对齐)
        # 间隔说明：输入框之间约3字符(0.2)，按钮前约5字符(0.35)
        c1, _, c2, _, c3, c4 = st.columns([1.2, 0.2, 1.2, 0.35, 0.8, 4], vertical_alignment="bottom")
        
        with c1:
            # 默认前4天
            default_start = date.today() - timedelta(days=4)
            in_start_date = st.date_input("数据起始日期", value=default_start, key="sel_start")
        with c2:
            in_end_date = st.date_input("数据结束日期", value=date.today(), key="sel_end")
        with c3:
            submit_select = st.form_submit_button("执行选股", type="primary")
    
    if submit_select:
        # 转换日期格式为 YYYYMMDD
        start_str = in_start_date.strftime('%Y%m%d')
        end_str = in_end_date.strftime('%Y%m%d')
        
        st.info(f"正在执行脚本: {script_path_select}")
        st.info(f"参数: {start_str} - {end_str}")
        
        run_script(script_path_select, [start_str, end_str])

# --- Tab 3: 日K线抽取 ---
with tab3:
    st.markdown('<span style="color: #C0C0C0;">拉取 Tushare 日线数据并存入数据库。</span>', unsafe_allow_html=True)
    
    script_path_update = os.path.join(os.path.dirname(__file__), "utils", "tushare_update_daily.py")
    
    with st.form("update_daily_form"):
        # 布局：2个条件 + 1个按钮 + 占位符 (靠左对齐)
        # 间隔说明：输入框之间约3字符(0.2)，按钮前约5字符(0.35)
        c1, _, c2, _, c3, c4 = st.columns([1.2, 0.2, 1.2, 0.35, 0.8, 4], vertical_alignment="bottom")
        
        with c1:
            in_update_start = st.date_input("开始日期", value=date.today(), key="upd_start")
        with c2:
            in_update_end = st.date_input("结束日期", value=date.today(), key="upd_end")
        with c3:
            submit_update = st.form_submit_button("开始抽取", type="primary")
        
    if submit_update:
        # 转换日期格式为 YYYYMMDD
        start_str = in_update_start.strftime('%Y%m%d')
        end_str = in_update_end.strftime('%Y%m%d')
        
        st.info(f"正在执行脚本: {script_path_update}")
        st.info(f"参数: {start_str} - {end_str}")
        
        run_script(script_path_update, [start_str, end_str])
        
    # 展示任务执行日志
    st.markdown("### 最近任务日志")
    df_logs = get_task_logs("日K线抽取", 20)
    if not df_logs.empty:
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("暂无执行记录")

# --- Tab 4: 数据管理 ---
with tab4:
    # 1. 获取选股日期下拉列表
    dates_list = []
    try:
        with engine.connect() as conn:
            # 仅查询有数据的日期，降序排列
            df_dates = pd.read_sql("SELECT DISTINCT execute_date FROM stock_selected ORDER BY execute_date DESC", conn)
            if not df_dates.empty:
                dates_list = df_dates['execute_date'].astype(str).tolist()
    except Exception as e:
        st.error(f"加载日期列表失败: {e}")

    # 布局：日期 | 时间 | 删除按钮 | 占位 (靠左对齐)
    # 间隔说明：输入框之间约3字符(0.2)，按钮前约5字符(0.35)
    c1, _, c2, _, c3, c4 = st.columns([1.2, 0.2, 1.2, 0.35, 0.8, 4], vertical_alignment="bottom")

    with c1:
        selected_date = st.selectbox(
            "选择选股日期", 
            options=dates_list,
            index=0 if dates_list else None,
            key="manage_date",
            placeholder="请选择日期"
        )

    # 2. 根据选择的日期获取对应的时间下拉列表
    times_list = []
    if selected_date:
        try:
            with engine.connect() as conn:
                query_time = text("SELECT DISTINCT execute_time FROM stock_selected WHERE execute_date = :date ORDER BY execute_time DESC")
                df_times = pd.read_sql(query_time, conn, params={"date": selected_date})
                if not df_times.empty:
                    times_list = df_times['execute_time'].astype(str).tolist()
        except Exception as e:
            st.error(f"加载时间列表失败: {e}")
            
    with c2:
        selected_time = st.selectbox(
            "选择选股时间", 
            options=times_list,
            index=0 if times_list else None,
            key="manage_time",
            placeholder="请选择时间"
        )

    with c3:
        delete_btn = st.button("删除记录", type="primary", key="del_btn")

    # 信息展示区 (优先显示 session_state 中的消息)
    if "manage_msg" in st.session_state:
        msg = st.session_state["manage_msg"]
        if msg["type"] == "success":
            st.success(msg["content"])
        elif msg["type"] == "error":
            st.error(msg["content"])
        elif msg["type"] == "warning":
            st.warning(msg["content"])
        elif msg["type"] == "info":
            st.info(msg["content"])

    if delete_btn:
        if not selected_date or not selected_time:
            st.warning("请先选择完整的日期和时间条件！")
        else:
            try:
                # 使用事务进行删除
                with engine.begin() as conn:
                    del_sql = text("DELETE FROM stock_selected WHERE execute_date = :date AND execute_time = :time")
                    result = conn.execute(del_sql, {"date": selected_date, "time": selected_time})
                    deleted_count = result.rowcount
                
                if deleted_count > 0:
                    # 存入 session_state 并立即刷新
                    st.session_state["manage_msg"] = {
                        "type": "success", 
                        "content": f"✅ 删除成功！共删除 {deleted_count} 条记录。\n(日期: {selected_date}, 时间: {selected_time})"
                    }
                    st.rerun()
                else:
                    st.info("未找到匹配的记录，未执行删除。")
                    
            except Exception as e:
                st.error(f"删除失败: {e}")

# --- Tab 5: 股票名称抽取 ---
with tab5:
    st.markdown('<span style="color: #C0C0C0;">从 BaoStock 抽取全部股票名称。</span>', unsafe_allow_html=True)
    
    script_path_names = os.path.join(os.path.dirname(__file__), "utils", "baostock_update_names.py")
    
    if st.button("抽取", type="primary", key="extract_names_btn"):
        st.info(f"正在执行脚本: {script_path_names}")
        run_script(script_path_names, [])
        
    # 展示任务执行日志
    st.markdown("### 最近任务日志")
    df_logs = get_task_logs("股票名称抽取", 20)
    if not df_logs.empty:
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("暂无执行记录")
