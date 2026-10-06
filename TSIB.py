from bs4 import BeautifulSoup

def TSIB(path, stock):
    with open(path, "r", encoding="utf-8") as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, 'html.parser')

    year = soup.find(id="lbExpired").get_text()
    data = []
    table = soup.find_all("table", width="795")[1]
    table_body = table.find("tbody")
    rows = table_body.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        cols = [ele.text.strip() for ele in cols]
        if cols:  # 確保該行有資料
            data.append([ele for ele in cols if ele])

    # 移除空列表
    data = [i for i in data if i]

    # 移除包含 "應收付" 的行
    data = [i for i in data if i[0] != "應收付"]

    temp = {}
    for i in range(0, len(data) - 2, 2):  # 每兩行處理一次
        
        if data[i][1]=='@':
            temp = {
            'date': f"{year}/{data[i][0]}",
            'stock_name': data[i][2],
            'quantity': data[i][3].replace(",", ""),
            'price': data[i][4].replace(",", ""),
            'fee': data[i][5].replace(",", ""),
            'type': data[i + 1][0].lstrip('@'),
            'number': data[i + 1][1].replace("(","").replace(")",""),
            'notional': data[i + 1][2].replace(",", ""),
        }
        else:
            temp = {
            'date': f"{year}/{data[i][0]}",
            'stock_name': data[i][1],
            'quantity': data[i][2].replace(",", ""),
            'price': data[i][3].replace(",", ""),
            'fee': data[i][4].replace(",", ""),
            'type': data[i + 1][0].lstrip('@'),
            'number': data[i + 1][1].replace("(","").replace(")",""),
            'notional': data[i + 1][2].replace(",", ""),
        }
        if temp['type'] == "現買":
            if temp['fee'] == '1':
                temp['discount'] = '0'
            else:
                temp['discount'] = data[i + 1][3].replace(",", "")
        else:
            temp['tax'] = data[i + 1][3]
            temp['discount'] = data[i + 1][4]
        stock.append(temp)
