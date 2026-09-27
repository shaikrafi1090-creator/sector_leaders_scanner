import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Custom Momentum Screener", layout="wide")
st.title("📈 Sector Leaders Momentum Screener")

# 1. Read stocks from the uploaded CSV file
@st.cache_data(ttl=86400)
def load_tickers_from_csv():
    try:
        # File name EXACTLY as provided
        df = pd.read_csv("sector leaders scanner csv.csv")
        # Clean symbols and add '.NS' for Yahoo Finance
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        tickers = (df['Symbol'] + ".NS").tolist()
        return tickers, df
    except FileNotFoundError:
        st.error("Error: 'sector leaders scanner csv.csv' file not found. Please ensure it's uploaded to GitHub.")
        return [], pd.DataFrame()

tickers, original_df = load_tickers_from_csv()

st.write(f"📂 Found **{len(tickers)}** stocks in **sector leaders scanner csv.csv**.")

# Scanning options
scan_mode = st.selectbox(
    "Select Stock Universe (Kitne stocks scan karne hain?):", 
    ["Top 50 Stocks (Fast Test - 1 min)", "Top 500 Stocks (Medium - 3 mins)", "All 1900+ Stocks (Takes 10+ mins)"]
)

if st.button("Run Scanner 🚀"):
    if not tickers:
        st.stop()
        
    with st.spinner("Downloading Data & Calculating... Please wait."):
        # Determine number of stocks to scan
        limit = 50 if "50 " in scan_mode else (500 if "500" in scan_mode else len(tickers))
        scan_tickers = tickers[:limit]
        
        # 2. Download Last 1 Year Data (~252 trading days)
        data = yf.download(scan_tickers, period="1y", group_by='ticker', threads=True, progress=False)
        
        # Extract 'Close' prices
        close_prices = pd.DataFrame()
        if len(scan_tickers) == 1:
            close_prices[scan_tickers[0]] = data['Close']
        else:
            for ticker in scan_tickers:
                if ticker in data and 'Close' in data[ticker]:
                    close_prices[ticker] = data[ticker]['Close']
                    
        close_prices.dropna(axis=1, how='all', inplace=True)
        
        # 3. Apply your Formula
        # Calculate daily percentage change: (close - prev_close) / prev_close * 100
        daily_returns = close_prices.pct_change() * 100
        
        # Calculating the 4 parts of your sum (Total 250 days lookback)
        sum_20 = daily_returns.iloc[-20:].sum()                      # Last 20 days sum
        sum_60 = daily_returns.iloc[-80:-20].sum()                   # 20 days ago, sum of 60 days
        sum_80 = daily_returns.iloc[-160:-80].sum()                  # 80 days ago, sum of 80 days
        sum_90 = daily_returns.iloc[-250:-160].sum()                 # 160 days ago, sum of 90 days
        
        # Total Formula Score
        total_score = sum_20 + sum_60 + sum_80 + sum_90
        
        # Create initial results dataframe
        results = pd.DataFrame({
            'Symbol': [t.replace('.NS', '') for t in total_score.index],
            'Last_20_Days': sum_20.values,
            'Days_20_to_80': sum_60.values,
            'Days_80_to_160': sum_80.values,
            'Days_160_to_250': sum_90.values,
            'Total_Score': total_score.values
        }).dropna()

        # Merge with CSV to get Stock Name and Sector
        results = pd.merge(results, original_df[['Symbol', 'Stock Name', 'sector']], on='Symbol', how='left')
        
        # 4. Filter Top 40% Stocks
        results = results.sort_values(by='Total_Score', ascending=False).reset_index(drop=True)
        top_40_count = max(1, int(len(results) * 0.40))
        top_40_df = results.head(top_40_count).copy()
        
        # 5. Divide into 3 categories (Green 33%, Gray 33%, Red 34%)
        green_cutoff = int(top_40_count * 0.33)
        gray_cutoff = int(top_40_count * 0.66)
        
        top_40_df['Category'] = 'Red' # Default bottom 34%
        if green_cutoff > 0:
            top_40_df.iloc[:green_cutoff, top_40_df.columns.get_loc('Category')] = 'Green'     # Top 33%
            top_40_df.iloc[green_cutoff:gray_cutoff, top_40_df.columns.get_loc('Category')] = 'Gray' # Middle 33%
            
        # Reorder columns & round decimals
        cols = ['Stock Name', 'Symbol', 'sector', 'Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250', 'Category']
        top_40_df = top_40_df[[c for c in cols if c in top_40_df.columns]]
        
        num_cols = ['Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250']
        top_40_df[num_cols] = top_40_df[num_cols].round(2)
        
        st.success(f"Scan Complete! Displaying Top 40% ({top_40_count} Stocks).")
        
        # 6. Apply Color Styling
        def style_rows(row):
            if row['Category'] == 'Green':
                return ['background-color: #c3e6cb; color: black'] * len(row)
            elif row['Category'] == 'Gray':
                return ['background-color: #d6d8d9; color: black'] * len(row)
            elif row['Category'] == 'Red':
                return ['background-color: #f5c6cb; color: black'] * len(row)
            return [''] * len(row)
            
        # Display table
        st.dataframe(top_40_df.style.apply(style_rows, axis=1), use_container_width=True, hide_index=True)
        
        # Download Button
        csv = top_40_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name='momentum_scan_results.csv',
            mime='text/csv',
        )
