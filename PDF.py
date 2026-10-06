from pathlib import Path
import re

import pdfplumber


DATE_PATTERN = re.compile(r"^@?\d{1,2}/\d{1,2}@?$")
YEAR_PATTERN = re.compile(r"(\d{4})年")


def _cell(row, index, path, row_number):
    try:
        value = row[index]
    except IndexError as error:
        raise ValueError(f"{path}: transaction row {row_number} is incomplete") from error
    if value is None:
        raise ValueError(f"{path}: transaction row {row_number} contains an empty required field")
    return str(value).strip()


def _clean_number(value):
    return value.replace(",", "")


def PDF(path, stock, pw):
    """Append transactions extracted from every table in a monthly statement."""
    year_match = YEAR_PATTERN.search(Path(path).name)
    if not year_match:
        raise ValueError(f"{path}: unable to determine statement year from filename")
    year = year_match.group(1)

    rows = []
    with pdfplumber.open(path, password=pw) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                rows.extend(table)

    for row_number, row in enumerate(rows):
        if not row:
            continue
        trade_date = _cell(row, 0, path, row_number)
        if not DATE_PATTERN.fullmatch(trade_date):
            continue

        settlement_row = next(
            (
                candidate
                for candidate in rows[row_number + 1:]
                if candidate and _cell(candidate, 0, path, row_number).strip()
            ),
            None,
        )
        if settlement_row is None:
            raise ValueError(f"{path}: transaction on row {row_number} has no settlement row")

        fee = _clean_number(_cell(row, 4, path, row_number))
        trade = {
            'date': f"{year}/{trade_date.replace('@', '')}",
            'number': _cell(row, 1, path, row_number).replace("(", "").replace(")", ""),
            'quantity': _clean_number(_cell(row, 2, path, row_number)),
            'price': _clean_number(_cell(row, 3, path, row_number)),
            'fee': fee,
            'type': _cell(settlement_row, 0, path, row_number + 1).lstrip('@'),
            'stock_name': _cell(settlement_row, 1, path, row_number + 1),
            'notional': _clean_number(_cell(settlement_row, 2, path, row_number + 1)),
        }
        if trade['type'] == "現買":
            trade['discount'] = '0' if fee == '1' else _clean_number(_cell(settlement_row, 4, path, row_number + 1))
        else:
            trade['tax'] = _clean_number(_cell(settlement_row, 3, path, row_number + 1))
            trade['discount'] = _clean_number(_cell(settlement_row, 4, path, row_number + 1))
        stock.append(trade)
