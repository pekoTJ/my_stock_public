# my_stock

Personal portfolio analysis and visualization tools. This repository contains no
personal transactions, broker statements, report outputs, or credentials.

## Local data setup

Copy the required files from `csv/*.example.csv` to the same names without
`.example`, then replace the sample rows with your own data. Runtime CSV files,
broker statements (`html/`, `pdf/`), generated reports, and strategy state are
ignored by Git.

If you import password-protected PDF statements, set the password locally before
running the importer:

```powershell
$env:MY_STOCK_PDF_PASSWORD = 'your-password'
```

Never commit that value, your source statements, or generated portfolio outputs.
