import tkinter as tk
import Stock
from config import PDF_PASSWORD
import os
import pandas as pd

def Read_data():
    listbox.delete(0,tk.END)
    dirPath=r"./html"
    stock=[]
    pw=PDF_PASSWORD
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
    
    sold,buy,fee,discount,pvalue,box=Stock.get_value(stock)
    listbox.insert('end',f'Sold         : {sold}')
    listbox.insert('end',f'Buy          : {buy}')
    listbox.insert('end',f'Spend        : {buy-sold}')
    listbox.insert('end',f'Present Value: {int(pvalue)}')
    listbox.insert('end',f'Unrealized   : {int(pvalue)-buy+sold}')

win = tk.Tk() # 如果使用直譯器的話，在這行Enter後就會先看到一個視窗了！
win.title('peko') # 更改視窗的標題
win.geometry('800x400') # 修改視窗大小(寬x高)
win.resizable(True, True) # 如果不想讓使用者能調整視窗大小的話就均設為False
win.iconbitmap('gura.ico') # 更改左上角的icon圖示

listbox = tk.Listbox(font='Courier',width='25',height='5')
listbox.pack(anchor='nw')

read_data = tk.Button(text="讀取",command=Read_data,width='42')
read_data.pack(anchor='nw')

win.mainloop() # 在一般python xxx.py的執行方式中，呼叫mainloop()才算正式啟動
