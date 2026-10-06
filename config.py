import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
CSV_DIR = PROJECT_DIR / 'csv'
HTML_DIR = PROJECT_DIR / 'html'
PDF_DIR = PROJECT_DIR / 'pdf'

# Environment variables override local defaults without requiring source changes.
PDF_PASSWORD = os.getenv('MY_STOCK_PDF_PASSWORD')
AUTO_REFRESH = os.getenv('MY_STOCK_AUTO_REFRESH', 'true').strip().lower() not in {
    '0', 'false', 'no', 'off'
}
