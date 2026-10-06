import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from config import CSV_DIR

class DataFetcher:
    """專責資料獲取"""
    def __init__(self, csv_dir=CSV_DIR):
        self.csv_dir = csv_dir
        os.makedirs(self.csv_dir, exist_ok=True)

    @staticmethod
    def download_market_data(tickers, start_date, end_date):
        yf_df = yf.download(tickers, start=start_date, end=end_date, auto_adjust=False)
        if yf_df.empty or 'Close' not in yf_df:
            return pd.DataFrame()

        close = yf_df['Close']
        if isinstance(close, pd.Series):
            return close.to_frame(name=tickers[0])
        return close

    @staticmethod
    def prepare_price_data(all_price, tickers, old_all_price, new_index):
        """Normalize prices while retaining cached values for unavailable tickers."""
        if all_price.empty:
            all_price = pd.DataFrame(index=new_index)

        rename_map = {col: str(col).replace('.TW', '').replace('GC=F', 'GOLD') for col in all_price.columns}
        all_price = all_price.rename(columns=rename_map)

        if 'TWD=X' in all_price.columns:
            if 'GOLD' in all_price.columns:
                all_price['GOLD'] = all_price['GOLD'] * all_price['TWD=X']
            all_price = all_price.drop(columns=['TWD=X'])
        elif 'GOLD' in all_price.columns:
            # Gold prices are only valid after converting USD to TWD.
            all_price = all_price.drop(columns=['GOLD'])

        all_price = all_price.round(2).reindex(new_index).ffill()
        all_price = all_price.combine_first(old_all_price).drop(new_index[-1], errors='ignore').ffill()
        return all_price

    @staticmethod
    def load_cached_price_data(csv_dir, index, columns):
        """Read cached prices without mutating the local data store."""
        price_path = os.path.join(csv_dir, 'All_Price.csv')
        all_price = pd.read_csv(price_path, index_col=0, encoding='utf-8', parse_dates=True)
        missing_columns = set(columns) - set(all_price.columns)
        if missing_columns:
            raise ValueError(f"Cached prices are missing: {', '.join(sorted(missing_columns))}")
        if all_price.index.max() < index.max():

            raise ValueError("Cached prices are out of date; call refresh_history() first.")

        return all_price.reindex(index).ffill()

class PortfolioCalculator:
    """專責財務計算"""
    @staticmethod
    def normalize_trade_type(value):
        """統一手動匯入與券商交易紀錄的交易類型。"""
        trade_type = str(value).strip().lstrip('@')
        return {'買進': '現買', '賣出': '現賣'}.get(trade_type, trade_type)

    @staticmethod
    def calculate_metrics(stock_trades):
        """計算財務數據"""
        sold = buy = fee = discount = pvalue = 0
        box = {}
        current_inventory = {}

        for trade in stock_trades:
            date = trade['date']
            number = trade['number']
            qty = float(trade['quantity'])
            
            # 計算庫存
            trade_type = PortfolioCalculator.normalize_trade_type(trade['type'])
            if trade_type in ('現買', '股利'):
                current_inventory[number] = current_inventory.get(number, 0) + qty
            elif trade_type == '現賣':
                current_inventory[number] = current_inventory.get(number, 0) - qty
                if current_inventory[number] <= 0:
                    current_inventory.pop(number, None)
            box[date] = current_inventory.copy()

            # 計算財務數據
            fee += float(trade.get('fee', 0))
            discount += float(trade.get('discount', 0))
            notional = float(trade.get('notional', 0))
            tax = float(trade.get('tax', 0))
            
            if trade_type == '現買':
                buy += (notional + float(trade.get('fee', 0)) - float(trade.get('discount', 0)))
            elif trade_type == '現賣':
                sold += (notional - float(trade.get('fee', 0)) - tax + float(trade.get('discount', 0)))

        return sold, buy, fee, discount, pvalue, box

    @staticmethod
    def process_history(box):
        """Build the daily inventory history without writing local files."""
        box_df = pd.DataFrame(data=box).T.fillna(0)
        box_df.index = pd.to_datetime(box_df.index)
        box_df.index.name = 'Date'
        
        # 建立完整的日期索引
        start_date = box_df.index.min()
        end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        new_index = pd.date_range(start=start_date, end=end_date, freq='D')
        box_df = box_df.reindex(new_index).drop(new_index[-1]).ffill().fillna(0)

        return box_df, new_index

    @staticmethod
    def save_history(stock_history, box_df, csv_dir=CSV_DIR):
        """Persist source transactions and calculated inventory during an explicit refresh."""
        os.makedirs(csv_dir, exist_ok=True)
        pd.DataFrame(data=stock_history).to_csv(
            os.path.join(csv_dir, 'All_Stock_History.csv'), encoding='utf-8'
        )
        box_df.to_csv(os.path.join(csv_dir, 'Stock_Inventory.csv'), encoding='utf-8')

    @staticmethod
    def get_cash_flow_rules(stock_history):
        """定義現金流計算規則"""
        stock_history['type'] = stock_history['type'].map(
            PortfolioCalculator.normalize_trade_type
        )
        numeric_columns = ['notional', 'fee', 'discount', 'tax']
        for column in numeric_columns:
            if column not in stock_history:
                stock_history[column] = 0
        stock_history[numeric_columns] = stock_history[numeric_columns].apply(
            pd.to_numeric, errors='coerce'
        ).fillna(0)
        is_buy = stock_history['type'] == '現買'
        stock_history['cost_cash_flow'] = np.where(is_buy, -(stock_history['notional'] + stock_history['fee'] - stock_history['discount']), 0)

        is_sold = stock_history['type'] == '現賣'
        stock_history['sold_cash_flow'] = np.where(is_sold, (stock_history['notional'] - stock_history['fee'] + stock_history['discount'] - stock_history['tax']), 0)

        is_div = stock_history['type'] == '利息'
        stock_history['dividends_cash_flow'] = np.where(is_div, (stock_history['notional'] - stock_history['fee']), 0)
        
        return stock_history

    @staticmethod
    def calculate_financials(stock_history, new_index, column_names):
        """計算累積現金流"""
        results = {}
        for col_name in column_names:
            cash_flow = stock_history.groupby(['date', 'number'])[col_name].sum().unstack(fill_value=0)
            df = pd.DataFrame(0, index=new_index, columns=cash_flow.columns)
            df.update(cash_flow)
            results[col_name.replace('_cash_flow', '')] = df.fillna(0).cumsum()
        return results

    @staticmethod
    def calculate_profit_breakdown(stock_trades, worth):
        """Calculate daily realized and unrealized profit using moving-average cost."""
        trades = pd.DataFrame(stock_trades).copy()
        if trades.empty:
            return pd.DataFrame(0, index=worth.index, columns=[
                'realized_profit', 'unrealized_profit', 'dividends', 'remaining_cost', 'market_value'
            ])

        trades['date'] = pd.to_datetime(trades['date'])
        trades = PortfolioCalculator.get_cash_flow_rules(trades)
        trades['quantity'] = pd.to_numeric(trades['quantity'], errors='coerce').fillna(0)
        trades = trades.sort_values('date', kind='stable')
        trades_by_date = {date: group for date, group in trades.groupby('date', sort=False)}

        positions = {}
        realized_profit = 0.0
        dividends = 0.0
        rows = []
        for date in worth.index:
            for trade in trades_by_date.get(date, pd.DataFrame()).itertuples(index=False):
                number = trade.number
                quantity = trade.quantity
                if trade.type == '現買':
                    quantity_on_hand, cost_on_hand = positions.get(number, (0.0, 0.0))
                    positions[number] = (
                        quantity_on_hand + quantity,
                        cost_on_hand + trade.notional + trade.fee - trade.discount,
                    )
                elif trade.type == '股利':
                    quantity_on_hand, cost_on_hand = positions.get(number, (0.0, 0.0))
                    positions[number] = (quantity_on_hand + quantity, cost_on_hand)
                elif trade.type == '現賣':
                    quantity_on_hand, cost_on_hand = positions.get(number, (0.0, 0.0))
                    if quantity > quantity_on_hand:
                        raise ValueError(f"{date.date()}: sell quantity exceeds inventory for {number}")
                    cost_basis = cost_on_hand * quantity / quantity_on_hand if quantity_on_hand else 0
                    proceeds = trade.notional - trade.fee - trade.tax + trade.discount
                    realized_profit += proceeds - cost_basis
                    remaining_quantity = quantity_on_hand - quantity
                    positions[number] = (remaining_quantity, cost_on_hand - cost_basis)
                elif trade.type == '利息':
                    dividends += trade.notional - trade.fee

            remaining_cost = sum(cost for _, cost in positions.values())
            market_value = worth.at[date, 'grand_total']
            rows.append({
                'realized_profit': realized_profit,
                'unrealized_profit': market_value - remaining_cost,
                'dividends': dividends,
                'remaining_cost': remaining_cost,
                'market_value': market_value,
            })
        return pd.DataFrame(rows, index=worth.index)

    @staticmethod
    def calculate_holding_details(stock_trades, inventory, worth):
        """Return current holdings valued with moving-average cost."""
        columns = [
            'number', 'average_cost', 'current_price', 'quantity', 'market_value',
            'profit', 'profit_pct', 'allocation_pct', 'largest_profit',
            'largest_loss', 'largest_position',
        ]
        trades = pd.DataFrame(stock_trades).copy()
        if trades.empty:
            return pd.DataFrame(columns=columns)

        trades['date'] = pd.to_datetime(trades['date'])
        trades = PortfolioCalculator.get_cash_flow_rules(trades)
        trades['quantity'] = pd.to_numeric(trades['quantity'], errors='coerce').fillna(0)
        trades = trades.sort_values('date', kind='stable')

        positions = {}
        for trade in trades.itertuples(index=False):
            quantity_on_hand, cost_on_hand = positions.get(trade.number, (0.0, 0.0))
            if trade.type == '現買':
                positions[trade.number] = (
                    quantity_on_hand + trade.quantity,
                    cost_on_hand + trade.notional + trade.fee - trade.discount,
                )
            elif trade.type == '股利':
                positions[trade.number] = (quantity_on_hand + trade.quantity, cost_on_hand)
            elif trade.type == '現賣':
                if trade.quantity > quantity_on_hand:
                    raise ValueError(f"{trade.date.date()}: sell quantity exceeds inventory for {trade.number}")
                cost_basis = cost_on_hand * trade.quantity / quantity_on_hand if quantity_on_hand else 0
                positions[trade.number] = (quantity_on_hand - trade.quantity, cost_on_hand - cost_basis)

        latest_inventory = inventory.iloc[-1]
        latest_worth = worth.iloc[-1]
        total_value = latest_worth['grand_total']
        rows = []
        for number, quantity in latest_inventory[latest_inventory > 0].items():
            quantity_on_hand, cost_on_hand = positions.get(number, (0.0, 0.0))
            average_cost = cost_on_hand / quantity_on_hand if quantity_on_hand else 0
            market_value = latest_worth.get(number, 0.0)
            current_price = market_value / quantity if quantity else 0
            profit = market_value - cost_on_hand
            rows.append({
                'number': number,
                'average_cost': average_cost,
                'current_price': current_price,
                'quantity': quantity,
                'market_value': market_value,
                'profit': profit,
                'profit_pct': profit / cost_on_hand * 100 if cost_on_hand else np.nan,
                'allocation_pct': market_value / total_value * 100 if total_value else np.nan,
            })

        details = pd.DataFrame(rows)
        if details.empty:
            return pd.DataFrame(columns=columns)
        details = details.sort_values('market_value', ascending=False).reset_index(drop=True)
        details['largest_profit'] = details['profit'].eq(details['profit'].max())
        details['largest_loss'] = details['profit'].eq(details['profit'].min())
        details['largest_position'] = details['market_value'].eq(details['market_value'].max())
        numeric_columns = [
            'average_cost', 'current_price', 'quantity', 'market_value',
            'profit', 'profit_pct', 'allocation_pct',
        ]
        details[numeric_columns] = details[numeric_columns].round(2)
        return details[columns]

    @staticmethod
    def calculate_range(data_min, data_max):
        if data_min > 1000:
            data_min -= 0.01 * data_min
        else:
            data_min -= 0.05 * abs(data_min)

        if data_max > 1000:
            data_max += 0.01 * data_max
        else:
            data_max += 0.05 * abs(data_max)
        
        return [data_min, data_max]
