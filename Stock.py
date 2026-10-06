# -*- coding: utf-8 -*-
from config import AUTO_REFRESH, CSV_DIR, HTML_DIR, PDF_DIR, PDF_PASSWORD
from portfolio_engine import DataFetcher, PortfolioCalculator
import os
import re
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pyxirr import xirr
from datetime import datetime
import ipywidgets as widgets
from IPython.display import display
import TSIB
import PDF

MANUAL_TRADES_PATH = CSV_DIR / 'Stock_not_in_file.csv'
VISIBILITY_LOG_PATH = os.path.join(os.path.dirname(__file__), 'visibility_debug.log')
CSV_DIR.mkdir(exist_ok=True)


def write_visibility_log(message):
    with open(VISIBILITY_LOG_PATH, 'a', encoding='utf-8') as log_file:
        log_file.write(f'{datetime.now().isoformat()} {message}\n')

class ChartManager:
    def __init__(self):
        self.is_locked = True

    def toggle_lock(self, trace, points, state):
        if points.point_inds:
            self.is_locked = not self.is_locked

chart_manager = ChartManager()


def merge_manual_trades(stock, path=MANUAL_TRADES_PATH):
    """Merge manually recorded trades without double-counting statement transactions."""
    if not os.path.exists(path):
        return

    manual_data = pd.read_csv(path, index_col=0, encoding='utf-8')
    required_columns = {'date', 'quantity', 'fee', 'type', 'number', 'notional'}
    if not required_columns.issubset(manual_data.columns):
        raise ValueError(f"{path}: missing required transaction columns")
    manual_trades = manual_data.to_dict('records')

    fields = ('date', 'stock_name', 'quantity', 'price', 'fee', 'type', 'number', 'notional', 'discount', 'tax')

    def trade_key(trade):
        return tuple('' if pd.isna(trade.get(field)) else str(trade.get(field)).strip() for field in fields)

    seen = {trade_key(trade) for trade in stock}
    for trade in manual_trades:
        key = trade_key(trade)
        if key not in seen:
            stock.append(trade)
            seen.add(key)
    stock.sort(key=lambda trade: pd.to_datetime(trade['date']))


def import_data(stock):
    # 這裡建議改為由一個配置或工廠類別處理
    for path in sorted(HTML_DIR.glob('*.html')):
        TSIB.TSIB(path, stock)
    for path in sorted(PDF_DIR.glob('*.pdf')):
        PDF.PDF(path, stock, PDF_PASSWORD)
    #merge_manual_trades(stock)

# get_web_content 已移除
# get_data 已移除
# get_value 已改為 PortfolioCalculator.calculate_metrics

def history(box, stock, refresh_market_data=None):
    """Calculate from cached prices and refresh automatically when the cache is insufficient."""
    pd.set_option("display.unicode.east_asian_width", True)
    
    # 1. 處理歷史數據與庫存
    calc = PortfolioCalculator()
    fetcher = DataFetcher(CSV_DIR)
    box_df, new_index = calc.process_history(box)
    
    # 2. 向量化計算現金流
    stock_history = pd.DataFrame(data=stock)
    stock_history['date'] = pd.to_datetime(stock_history['date'])
    stock_history = calc.get_cash_flow_rules(stock_history)
    
    financials = calc.calculate_financials(
        stock_history, new_index, 
        ['cost_cash_flow', 'sold_cash_flow', 'dividends_cash_flow']
    )
    cost, sold, dividends = financials['cost'], financials['sold'], financials['dividends']
    
    # 3. 市場資料處理
    tickers = [f"{col}.TW" if col != 'GOLD' else 'GC=F' for col in box_df.columns if col != 'grand_total']
    if 'GOLD' in box_df.columns: tickers.append("TWD=X")
    tickers.append("^VIX")

    price_columns = [*box_df.columns, '^VIX']
    if refresh_market_data is None:
        refresh_market_data = False
    if not refresh_market_data:
        try:
            all_price = fetcher.load_cached_price_data(CSV_DIR, box_df.index, price_columns)
        except (FileNotFoundError, ValueError):
            if not AUTO_REFRESH:
                raise
            refresh_market_data = True

    if refresh_market_data:
        price_path = os.path.join(CSV_DIR, 'All_Price.csv')
        if os.path.exists(price_path):
            old_all_price = pd.read_csv(price_path, index_col=0, encoding='utf-8', parse_dates=True)
            start_date = old_all_price.index[-1]
        else:
            old_all_price = pd.DataFrame()
            start_date = new_index[0]
        raw_all = fetcher.download_market_data(tickers, start_date, new_index[-1])
        all_price = fetcher.prepare_price_data(raw_all, tickers, old_all_price, new_index)
        calc.save_history(stock_history.to_dict('records'), box_df, CSV_DIR)
        all_price.to_csv(os.path.join(CSV_DIR, 'All_Price.csv'), encoding='utf-8')
    
    # 4. 總資產計算
    worth = box_df * all_price
    worth['grand_total'] = worth.sum(axis=1)
    worth['^VIX'] = all_price['^VIX'].copy()
    worth = worth.round(2)
    if refresh_market_data:
        worth.to_csv(os.path.join(CSV_DIR, 'Daily_Worth.csv'), encoding='utf-8')
    
    return worth, int(worth['grand_total'].iloc[-1]), box_df, cost, sold, dividends


def refresh_history(box, stock):
    """Explicitly download market data and refresh all derived CSV files."""
    return history(box, stock, refresh_market_data=True)

def show_2_chart(box,inventory,cost,sold,dividends,df_xirr,profit_breakdown=None):
    hide_amounts = False
    last_summary_values = ''
    current_title_date = box.index[-1].strftime('%Y-%m-%d')

    def chart_title(total_value):
        if hide_amounts:
            return f"日期：{current_title_date}"
        return f"日期：{current_title_date}, 總價值：{total_value:.0f}"

    def mask_summary_amounts(summary_values):
        lines = summary_values.split('<br>')
        for index in range(1, min(9, len(lines))):
            lines[index] = re.sub(r'^-?[\d,]+(?:\.\d+)?', '****', lines[index])
        return '<br>'.join(lines)

    color_map = {
        '0050':'#1f77b4',
        '0056':'#ff7f0e',
        '00878': '#7f7f7f',
        '006208':"#9c3030",
        '00922':'#9467bd',
        '00923':'#8c564b',
        '2887':'#e377c2',
        '2891':'#2ca02c',
        '2330':"#ff0000",
        '2603':'#17becf',
        '2376':'#aec7e8',
        '00981A':'#ffbb78',
        '00757':'#98df8a',
        '00646':'#ff9896',
        '2454':"#ff8400",
        'GOLD':"#e5bf13",
        'grand_total':'#1b0c5e'
    }
# 定義根據 X 軸索引更新的函式 >>>
    def update_pie_charts(trace, points, state):
        nonlocal current_title_date, last_summary_values
        if chart_manager.is_locked or not points.point_inds:
            return
        
        idx = points.point_inds[0]
        
        # 1. 提早做好切片：只抓出數值 > 0 的項目，並排除最後一筆
        active_data = box.iloc[idx][box.iloc[idx] > 0][:-1]
        previous_idx = max(idx - 1, 0)
        pre_active_data = box.iloc[previous_idx][box.iloc[idx] > 0][:-1].replace(0, 1)
        labels = active_data.index.tolist()
        
        # 2. 準備對應的顏色與額外資訊 (長度現在完全一致了)
        current_colors = [color_map.get(lbl, '#CCCCCC') for lbl in labels]
        
        cost_data = cost.iloc[idx].loc[labels]
        sold_data = sold.iloc[idx].loc[labels]
        dividends_data = dividends.iloc[idx].loc[labels]
        profit_pct = (cost_data + sold_data + dividends_data + active_data) / abs(cost_data) * 100
        difference = active_data - pre_active_data
        difference_pct = difference / pre_active_data
        extra_data = np.column_stack((cost_data, profit_pct, difference, difference_pct))
        
        #annotation >>>
        days = len(box.iloc[:idx + 1])
        years = days / 365.25
        f_sold = sold.iloc[idx].sum()
        f_dividends = dividends.iloc[idx].sum()
        buy = cost.iloc[idx].sum() * -1
        spend = buy - f_sold - f_dividends
        pvalue = box.iloc[idx,:-1].sum()
        profit = pvalue - buy + f_sold + f_dividends
        previous_total = box.iloc[previous_idx]['grand_total']
        change = box.iloc[idx]['grand_total'] - previous_total
        change_pct = change / previous_total if previous_total else 0
        ROI = (profit / buy)
        cagr = ((1 + ROI) ** (1 / years) - 1) * 100
        new_data = pd.DataFrame([{
            'date': box.index[idx].strftime('%Y/%m/%d'),
            'net_cash': pvalue
        }])
        df_xirr2 = pd.concat([df_xirr[:-1][df_xirr['date'].astype('datetime64[s]') <= box.index[idx]], new_data], ignore_index=True)
        xirr_rate = xirr(df_xirr2['date'].astype('datetime64[s]'), df_xirr2['net_cash'].astype(int))

        current_annos = list(fw.layout.annotations)
        if profit_breakdown is None:
            last_summary_values = f"<b></b><br>{f_sold:.0f}<br>{buy:.0f}<br>{spend:.0f}<br>{f_dividends:.0f}<br>{pvalue:.0f}<br>{profit:.0f}({ROI * 100:.2f}%)<br>{change:.0f}({change_pct:.2%})<br>{days}<br>{cagr:.2f}%<br>{xirr_rate:.2%}<br>"
        else:
            breakdown = profit_breakdown.iloc[idx]
            total_profit = breakdown['realized_profit'] + breakdown['unrealized_profit'] + breakdown['dividends']
            unrealized_profit_pct = breakdown['unrealized_profit'] / breakdown['remaining_cost'] * 100 if breakdown['remaining_cost'] else 0
            last_summary_values = f"<b></b><br>{f_sold:.0f}<br>{buy:.0f}<br>{spend:.0f}<br>{breakdown['realized_profit']:.0f}<br>{breakdown['unrealized_profit']:.0f}({unrealized_profit_pct:.2f}%)<br>{breakdown['dividends']:.0f}<br>{total_profit:.0f}({ROI * 100:.2f}%)<br>{change:.0f}({change_pct:.2%})<br>{days}<br>{cagr:.2f}%<br>{xirr_rate:.2%}<br>"
        current_annos[summary_values_annotation_index].text = mask_summary_amounts(last_summary_values) if hide_amounts else last_summary_values
        #annotation <<<

        # 3. 批量更新圖表
        with fw.batch_update():
            pie_trace.values = active_data
            pie_trace.labels = labels
            pie_trace.marker.colors = current_colors
            pie_trace.customdata = extra_data.tolist()
            # 更新標題
            current_title_date = box.index[idx].strftime('%Y-%m-%d')
            fw.layout.title.text = chart_title(box.iloc[idx]['grand_total'])
            fw.layout.uirevision = 'keep_it_fixed'
            # 更新資料
            fw.layout.annotations = current_annos
    # 定義根據 X 軸索引更新的函式 <<<

    def toggle_lock_wrapper(trace, points, state):
        chart_manager.toggle_lock(trace, points, state)

    def update_profit_traces(percent, label):
        percent = pd.Series(percent, index=percent.index).reindex(box.index).ffill()
        percent_values = percent.to_numpy().tolist()
        total_trace.y = percent_values
        total_trace.name = label + '_PCT'
        total_ma30_trace.y = percent.rolling(window=30, min_periods=1).mean().tolist()
        total_ma30_trace.name = label + '_PCT_MA30'
        total_ma90_trace.y = percent.rolling(window=90, min_periods=1).mean().tolist()
        total_ma90_trace.name = label + '_PCT_MA90'

    def update_chart_2(trace, points, state):
        if not points.point_inds:
            return
        
        clicked_label = trace.labels[points.point_inds[0]]
        profit = cost[clicked_label] + sold[clicked_label] + dividends[clicked_label] + box[clicked_label].ffill()
        percent = profit / abs(cost[clicked_label]) * 100
        Profit_PCT_MA30 = percent.rolling(window=30, min_periods=1).mean()
        Profit_PCT_MA90 = percent.rolling(window=90, min_periods=1).mean()
        with fw.batch_update():
            update_profit_traces(percent, clicked_label)
            fw.layout.uirevision = 'keep_it_fixed'
        update_y_axis_limit(None, None)

    def update_y_axis_limit(obj, change):
        x_range = fw.layout.xaxis.range
        if x_range is None or x_range[0] is None or x_range[1] is None:
            start, end = box.index[0], box.index[-1]
        else:
            start = pd.to_datetime(x_range[0]).tz_localize(None)
            end = pd.to_datetime(x_range[1]).tz_localize(None)
        indices = np.where((box.index >= start) & (box.index <= end))[0]
        if not len(indices):
            return
        start_idx = indices[0]
        end_idx = indices[-1]+1
        with fw.batch_update():
            visible_box = box.iloc[start_idx:end_idx]
            visible_portfolio_values = []
            active_portfolio_trace = next(
                (trace for trace in portfolio_traces if trace.visible is True),
                None,
            )
            if active_portfolio_trace is not None and len(active_portfolio_trace.y):
                values = np.asarray(active_portfolio_trace.y[start_idx:end_idx], dtype=float)
                visible_portfolio_values.extend(values[np.isfinite(values)])
            if visible_portfolio_values:
                fw.layout.yaxis.range = PortfolioCalculator.calculate_range(min(visible_portfolio_values), max(visible_portfolio_values))
            fw.layout.yaxis.autorange = False
            visible_values = []
            for trace in fw.data:
                if getattr(trace, 'xaxis', None) != 'x2' or trace.visible is False or trace.visible == 'legendonly' or not len(trace.y):
                    continue
                values = np.asarray(trace.y[start_idx:end_idx], dtype=float)
                visible_values.extend(values[np.isfinite(values)])
            if visible_values:
                fw.layout.yaxis2.range = PortfolioCalculator.calculate_range(min(visible_values), max(visible_values))
                fw.layout.yaxis2.autorange = False

    visibility_callback_busy = False

    def update_portfolio_visibility(trace, change):
        nonlocal visibility_callback_busy
        if visibility_callback_busy:
            return
        write_visibility_log(f'[visibility] start: {trace.name} visible={trace.visible!r}')
        write_visibility_log(f'[visibility] portfolio={[(item.name, repr(item.visible)) for item in portfolio_traces]}')
        if trace.visible is False or trace.visible == 'legendonly':
            if not any(portfolio_trace.visible is True for portfolio_trace in portfolio_traces):
                visibility_callback_busy = True
                grand_total_trace.visible = True
                total_group = (total_trace, total_ma30_trace, total_ma90_trace)
                with fw.batch_update():
                    update_profit_traces(df_profit_trend['total_percent'], 'Profit')
                    for total_group_trace in total_group:
                        total_group_trace.visible = True
                update_y_axis_limit(None, None)
                visibility_callback_busy = False
                write_visibility_log('[visibility] restored grand_total')
            return
        if trace.visible is not True:
            return
        visibility_callback_busy = True
        total_group = (total_trace, total_ma30_trace, total_ma90_trace)
        with fw.batch_update():
            for portfolio_trace in portfolio_traces:
                if portfolio_trace is not trace:
                    portfolio_trace.visible = 'legendonly'
            if trace.name == 'grand_total':
                for total_group_trace in total_group:
                    total_group_trace.visible = True
                update_profit_traces(df_profit_trend['total_percent'], 'Profit')
            else:
                profit = cost[trace.name] + sold[trace.name] + dividends[trace.name]
                profit = profit + box[trace.name].ffill()
                update_profit_traces(profit / abs(cost[trace.name]) * 100, trace.name)
                for total_group_trace in total_group:
                    total_group_trace.visible = True
        write_visibility_log(f'[visibility] end: {[(item.name, repr(item.visible)) for item in portfolio_traces]}')
        write_visibility_log(f'[visibility] lower={[(item.name, len(item.y) if item.y is not None else None, repr(item.visible)) for item in total_group]}')
        update_y_axis_limit(None, None)
        visibility_callback_busy = False

#===========================================================================================
    box = box.fillna(0)
    vix = box['^VIX'].copy()
    box = box.drop(columns = ['^VIX'])
    if profit_breakdown is not None:
        profit_breakdown = profit_breakdown.reindex(box.index).ffill().fillna(0)

    # 資料計算 >>>
    days = len(box)
    years = days / 365.25
    f_sold = sold.iloc[-1].sum()
    f_dividends = dividends.iloc[-1].sum()
    buy = cost.iloc[-1].sum() * -1
    spend = buy - f_sold - f_dividends
    pvalue = box.iloc[-1,:-1].sum()
    profit = pvalue - buy + f_sold + f_dividends
    previous_row = box.iloc[max(len(box) - 2, 0)]
    change = box.iloc[-1]['grand_total'] - previous_row['grand_total']
    change_pct = change / previous_row['grand_total'] if previous_row['grand_total'] else 0
    ROI = (profit / buy)
    cagr = ((1 + ROI) ** (1 / years) - 1) * 100
    new_data = pd.DataFrame([{
        'date': datetime.now().strftime('%Y-%m-%d'),
        'net_cash': pvalue
    }])
    df_xirr = pd.concat([df_xirr, new_data], ignore_index=True)
    xirr_rate = xirr(df_xirr['date'].astype('datetime64[s]'), df_xirr['net_cash'].astype(int))
    #-----------------------------------------------------------------------------------------
    total_cost = cost.sum(axis = 1)
    total_sold = sold.sum(axis = 1)
    total_dividends = dividends.sum(axis = 1)
    total_profit = total_cost + total_sold + total_dividends + box.iloc[:,-1]
    df_profit_trend = pd.DataFrame({
        'total_percent': (total_profit / abs(total_cost)) * 100
    })
    df_profit_trend['Profit_PCT_MA30'] = df_profit_trend['total_percent'].rolling(window=30, min_periods=1).mean()
    df_profit_trend['Profit_PCT_MA90'] = df_profit_trend['total_percent'].rolling(window=90, min_periods=1).mean()


    initial_values = box.iloc[-1][box.iloc[-1] > 0][:-1]  # 直接篩選 >0 並排除最後一項
    pre_initial_values = previous_row[box.iloc[-1] > 0][:-1].replace(0, 1)
    labels = initial_values.index.tolist()
    #-----------------------------------------------------------------------------------------
    cost_data = cost.iloc[-1].loc[labels]
    sold_data = sold.iloc[-1].loc[labels]
    dividends_data = dividends.iloc[-1].loc[labels]
    profit_pct = (cost_data + sold_data + dividends_data + initial_values) / abs(cost_data) * 100
    difference = initial_values - pre_initial_values
    difference_pct = difference / pre_initial_values
    extra_data = np.column_stack((cost_data, profit_pct, difference, difference_pct)) # 使用 column_stack 更直覺

    # 資料計算 <<<
    
    # 1. 建立子圖
    fig = make_subplots(
        rows=2, cols=2,
        column_widths=[0.65, 0.35], row_heights=[0.5, 0.5],
        specs=[[{"type": "xy"}, {"type": "domain"}], [{"type": "xy"}, None]],
        subplot_titles=("資產配置分布 (市值)", "", "資產報酬率(%)",),
        vertical_spacing=0.05, # 調整上下子圖的間距，避免文字重疊
        horizontal_spacing=0.05,
        shared_xaxes=True
    )
    
    # 2. 設定 Layout (簡化 title 寫法)
    fig.update_layout(
        hovermode='x unified', width=1200, height=800, #yaxis2_range=[ -20, 80],
        title=chart_title(box.iloc[-1]['grand_total'])
    )
    
    # 合併 X 軸設定，一次套用到底下的所有 X 軸
    last_date = box.index[-1]
    start_view_date = box.index[-min(30, len(box))]
    fig.update_xaxes(row=1, col=1, rangeselector=dict(buttons=list([dict(count=1, label="1m", step="month", stepmode="backward"), dict(count=3, label="3m", step="month", stepmode="backward"), dict(count=6, label="6m", step="month", stepmode="backward"), dict(count=1, label="YTD", step="year", stepmode="todate"), dict(count=1, label="1Y", step="year", stepmode="backward"), dict(count=len(box.index), label="All", step="day", stepmode="backward")])))
    fig.update_xaxes(type="date", range=[start_view_date, last_date], rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(row=1, col=1, range=PortfolioCalculator.calculate_range(min(box.iloc[-32:]['grand_total']), max(box.iloc[-32:]['grand_total'])))#[min(box.iloc[-32:]['grand_total'])*0.99, max(box.iloc[-32 :]['grand_total'])*1.01])
    fig.update_yaxes(row=2, col=1, showgrid=False, autorange=False)
    if profit_breakdown is None:
        summary_labels = "<b>投資摘要</b><br>Sold :<br>Buy :<br>Spend :<br>Dividends :<br>Present Value :<br>Profit :<br>Change :<br>Investment days :<br>CAGR :<br>XIRR :<br>"
        summary_values = f"<b></b><br>{f_sold:.0f}<br>{buy:.0f}<br>{spend:.0f}<br>{f_dividends:.0f}<br>{pvalue:.0f}<br>{profit:.0f}({ROI * 100:.2f}%)<br>{change:.0f}({change_pct:.2%})<br>{days}<br>{cagr:.2f}%<br>{xirr_rate:.2%}<br>"
    else:
        breakdown = profit_breakdown.iloc[-1]
        total_profit = breakdown['realized_profit'] + breakdown['unrealized_profit'] + breakdown['dividends']
        unrealized_profit_pct = breakdown['unrealized_profit'] / breakdown['remaining_cost'] * 100 if breakdown['remaining_cost'] else 0
        summary_labels = "<b>投資摘要</b><br>Sold :<br>Buy :<br>Spend :<br>Realized Profit :<br>Unrealized Profit :<br>Dividends :<br>Total Profit :<br>Change :<br>Investment days :<br>CAGR :<br>XIRR :<br>"
        summary_values = f"<b></b><br>{f_sold:.0f}<br>{buy:.0f}<br>{spend:.0f}<br>{breakdown['realized_profit']:.0f}<br>{breakdown['unrealized_profit']:.0f}({unrealized_profit_pct:.2f}%)<br>{breakdown['dividends']:.0f}<br>{total_profit:.0f}({ROI * 100:.2f}%)<br>{change:.0f}({change_pct:.2%})<br>{days}<br>{cagr:.2f}%<br>{xirr_rate:.2%}<br>"
    last_summary_values = summary_values

    # 加入文字
    fig.add_annotation(
        text=summary_labels,
        xref="paper", yref="paper", 
        x=0.83, y=0.1,    # 手動調到右下角
        showarrow=False,
        font=dict(size=16, color="darkblue"),
        align="left"
    )
    fig.add_annotation(
        text=summary_values,
        xref="paper", yref="paper", 
        x=1.0, y=0.1,    # 手動調到右下角
        showarrow=False,
        font=dict(size=16, color="darkblue"),
        align="left"
    )

    # 3. 加入上方折線圖 (多支股票)
    column = box.iloc[-1][box.iloc[-1] > 0].sort_values(ascending=False)
    column = pd.concat([box.iloc[-1][box.iloc[-1] <= 0], column])
    #box_none = box.replace(0,None)
    for col in column.index:
        if col == 'grand_total':
            fig.add_trace(
                go.Scatter(x=box.index, y=box[col].astype(int), name=col, connectgaps=True, mode='lines', hoverinfo='x+name+y', marker=dict(color=color_map.get(col, '#CCCCCC'))),
                row=1, col=1
            )
        else:
            if box.iloc[-1].loc[col]>0:
                fig.add_trace(
                    go.Scatter(x=box.index, y=box[col], name=col, connectgaps=True, mode='lines', hoverinfo='skip', fillcolor=color_map.get(col, '#CCCCCC'), marker=dict(color=color_map.get(col, '#CCCCCC')), visible='legendonly'),#stackgroup='one',
                    #go.Scatter(x=box.index, y=box[col], name=col, connectgaps=False, mode='lines', hoverinfo='skip', fillcolor=color_map[col], stackgroup='one', marker=dict(color=color_map[col])),
                    row=1, col=1
                )
            '''
            else:
                fig.add_trace(
                    go.Scatter(x=box.index, y=box[col], name=col, connectgaps=True, mode='lines', hoverinfo='skip', fillcolor=color_map[col], visible='legendonly', marker=dict(color=color_map[col])),#stackgroup='one',
                    #go.Scatter(x=box.index, y=box[col], name=col, connectgaps=False, mode='lines', hoverinfo='skip', fillcolor=color_map[col], visible='legendonly', stackgroup='one', marker=dict(color=color_map[col])),
                    row=1, col=1
                )
            '''

    # 加入下方總獲利折線圖
    '''
    total_percent = (total_profit / abs(total_cost + total_sold + total_dividends)) * 100
    fig.add_trace(
        go.Scatter(
            x=cost.index, y=total_percent, connectgaps=True, mode='lines', name='total_profit/spend', visible='legendonly',
            hovertemplate='<b>%{y:,.2f}%</b>', marker=dict(color="#1383e5")
        ),
        row=2, col=1
    )
    '''
    fig.update_yaxes(row=2, col=1, range=PortfolioCalculator.calculate_range(df_profit_trend[['total_percent', 'Profit_PCT_MA30', 'Profit_PCT_MA90']].iloc[-32:].min().min(), df_profit_trend[['total_percent', 'Profit_PCT_MA30', 'Profit_PCT_MA90']].iloc[-32:].max().max()))
    fig.add_trace(
        go.Scatter(
            x=box.index, y=df_profit_trend['total_percent'].reindex(box.index), connectgaps=True, mode='lines', name='Profit_PCT',
            hovertemplate='<b>%{y:,.2f}%</b>', marker=dict(color="#ed1010")
        ),
        row=2, col=1
    )
    # 加入均線
    fig.add_trace(
        go.Scatter(
            x=box.index, y=df_profit_trend['Profit_PCT_MA30'].reindex(box.index), connectgaps=True, mode='lines', name='Profit_PCT_MA30',
            hovertemplate='<b>%{y:,.2f}%</b>', marker=dict(color="#1f10ed")
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=box.index, y=df_profit_trend['Profit_PCT_MA90'].reindex(box.index), connectgaps=True, mode='lines', name='Profit_PCT_MA90',
            hovertemplate='<b>%{y:,.2f}%</b>', marker=dict(color="#e98f07")
        ),
        row=2, col=1
    )
    # 加入vix
    fig.add_trace(
        go.Scatter(
            x=vix.index, y=vix, connectgaps=True, mode='lines', name='VIX', visible='legendonly',
            hovertemplate='<b>%{y:,.2f}</b>', marker=dict(color="#8a10ed")
        ),
        row=2, col=1
    )
    # 4. 加入下方獲利折線圖 (空圖表)``

    # 5. 加入初始圓餅圖 (優化切片與合併邏輯)
    fig.add_trace(
        go.Pie(
            name='Allocation', labels=labels, values=initial_values, textinfo='label+percent', customdata=extra_data.tolist(),
            #hovertemplate="<b>%{label}</b><br>現值: %{value:,.0f} 元(%{customdata[0][1]:,.2f}%)<br>佔比: %{percent}<extra></extra>",
            hovertemplate="<b>%{label}</b><br>現值: %{value:,.0f} 元(%{customdata[0][1]:,.2f}%)<br>當日漲跌: %{customdata[0][2]:,.0f} 元(%{customdata[0][3]:.2%})<br>佔比: %{percent}<extra></extra>",
            marker=dict(colors=[color_map.get(lbl, '#CCCCCC') for lbl in labels])
        ),
        row=1, col=2
    )

    fw = go.FigureWidget(fig)

    # 6. 綁定監聽事件
    traces_by_name = {trace.name: trace for trace in fw.data}
    portfolio_traces = [traces_by_name[column] for column in box.columns if column in traces_by_name]
    total_trace = traces_by_name['Profit_PCT']
    total_ma30_trace = traces_by_name['Profit_PCT_MA30']
    total_ma90_trace = traces_by_name['Profit_PCT_MA90']
    vix_trace = traces_by_name['VIX']
    pie_trace = traces_by_name['Allocation']
    summary_values_annotation_index = len(fw.layout.annotations) - 1
    grand_total_trace = traces_by_name['grand_total']

    amount_toggle = widgets.ToggleButton(
        value=False,
        description='隱藏金額',
        icon='eye-slash',
        tooltip='切換投資摘要的金額顯示',
    )

    def toggle_amount_visibility(change):
        nonlocal hide_amounts
        hide_amounts = change['new']
        amount_toggle.description = '顯示金額' if hide_amounts else '隱藏金額'
        amount_toggle.icon = 'eye' if hide_amounts else 'eye-slash'
        fw.layout.title.text = chart_title(box.loc[pd.to_datetime(current_title_date), 'grand_total'])
        fw.layout.yaxis.showticklabels = not hide_amounts
        fw.layout.annotations[summary_values_annotation_index].text = (
            mask_summary_amounts(last_summary_values) if hide_amounts else last_summary_values
        )

    amount_toggle.observe(toggle_amount_visibility, names='value')
    display(amount_toggle)

    for trace in portfolio_traces:
        trace.on_hover(update_pie_charts)
        trace.on_click(toggle_lock_wrapper)
        trace.on_change(update_portfolio_visibility, 'visible')

    #pie_trace.on_hover(update_chart_2)
    fw.layout.xaxis.on_change(update_y_axis_limit, 'range') # 監聽 X 軸範圍變化
    vix_trace.on_change(update_y_axis_limit, 'visible')
    update_y_axis_limit(None, None)
    return fw
