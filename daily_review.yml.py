name: Daily Market Review

on:
  schedule:
    # 香港時間 17:00 = UTC 09:00，週一至週五
    - cron: '0 9 * * 1-5'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run-review:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      
      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run Stock Review
        run: python daily_review.py
        env:
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
