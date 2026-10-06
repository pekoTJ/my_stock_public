import Stock
from config import CSV_DIR, PDF_PASSWORD
import os
import pandas as pd
import time
import yfinance as yf
from datetime import datetime, timedelta
import plotly.express as px #動態圖表
from dash import Dash, dcc, html



stock=[]
pw=PDF_PASSWORD
read_html_pdf = 0 # 0:從csv讀資料 / 1:從html跟pdf讀資料

if read_html_pdf:
    choice='1'
    filetype='html'
    dirPath=r"./"+filetype
    result = [f'./{filetype}/'+f for f in os.listdir(dirPath)if os.path.isfile(os.path.join(dirPath,f))and f[-1*len(filetype):]==filetype]
    for p in result: 
        Stock.import_data(choice,p,stock,pw)
    choice='2'
    filetype='pdf'
    dirPath=r"./"+filetype
    result = [f'./{filetype}/'+f for f in os.listdir(dirPath)if os.path.isfile(os.path.join(dirPath,f))and f[-1*len(filetype):]==filetype]
    for p in result: 
        Stock.import_data(choice,p,stock,pw)
    stock=pd.DataFrame(data=stock)
    gold=pd.read_csv(CSV_DIR / 'gold.csv',index_col=0,encoding='utf-8')
    dividends_file=pd.read_csv(CSV_DIR / 'Dividends_History.csv',index_col=0,encoding='utf-8')
    combined_df = pd.concat([stock, gold, dividends_file], axis=0)
    combined_df.index = pd.to_datetime(combined_df['date'])
    stock = combined_df.sort_index().to_dict('records')[1:]
else:
    stock=pd.read_csv(CSV_DIR / 'Stock_History.csv',index_col=0,encoding='utf-8').to_dict('records')


sold,buy,fee,discount,pvalue,box1 = Stock.get_value(stock)
box,pvalue,inventory,cost,df_sold, dividends = Stock.history(box1,stock)

profit = pvalue - buy + df_sold.iloc[-1].sum() + dividends.iloc[-1].sum()
spend = buy - sold - dividends.iloc[-1].sum()
days = len(box)
years = days / 365.25
total_return = profit / buy
cagr = ((1 + total_return) ** (1 / years) - 1) * 100

print(f'Sold           : {df_sold.iloc[-1].sum():.0f}')
print(f'Buy            : {buy:.0f}')
print(f'Spend          : {spend:.0f}')
print(f'dividends      : {dividends.iloc[-1].sum():.0f}')
print(f'Present Value  : {pvalue:.0f}')
print(f'profit         : {profit:.0f}({((total_return) * 100):.2f}%)')
print(f'Investment days: {days}')
print(f'CAGR           : {cagr:.2f}%')

fw = Stock.show_2_chart(box,inventory,cost,df_sold,dividends)
#fw.show()
app = Dash(__name__)

app.layout = html.Div([
    dcc.Graph(figure=fw)
])
app.run(debug=True)
