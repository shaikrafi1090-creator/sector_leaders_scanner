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
        df = pd.read_csv("sector leaders scanner csv.csv")
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        tickers = (df['Symbol'] + ".NS").tolist()
        return tickers, df
    except FileNotFoundError:
        st.error("Error: 'sector leaders scanner csv.csv' file not found. Please ensure it's uploaded to GitHub.")
        return [], pd.DataFrame()

tickers, original_df = load_tickers_from_csv()

st.write(f"📂 Found **{len(tickers)}** stocks in **sector leaders scanner csv.csv**.")

scan_mode = st.selectbox(
    "Select Stock Universe (Kitne stocks scan karne hain?):", 
    ["Top 50 Stocks (Fast Test - 1 min)", "Top 500 Stocks (Medium - 3 mins)", "All 1900+ Stocks (Takes 10+ mins)"]
)

if st.button("Run Scanner 🚀"):
    if not tickers:
        st.stop()
        
    with st.spinner("Downloading Data & Calculating... Please wait."):
        limit = 50 if "50 " in scan_mode else (500 if "500" in scan_mode else len(tickers))
        scan_tickers = tickers[:limit]
        
        # 2. Download Data
        data = yf.download(scan_tickers, period="1y", group_by='ticker', threads=True, progress=False)
        
        close_prices = pd.DataFrame()
        if len(scan_tickers) == 1:
            close_prices[scan_tickers[0]] = data['Close']
        else:
            for ticker in scan_tickers:
                if ticker in data and 'Close' in data[ticker]:
                    close_prices[ticker] = data[ticker]['Close']
                    
        close_prices.dropna(axis=1, how='all', inplace=True)
        
        # 3. Apply Formula
        daily_returns = close_prices.pct_change() * 100
        
        sum_20 = daily_returns.iloc[-20:].sum()                      
        sum_60 = daily_returns.iloc[-80:-20].sum()                   
        sum_80 = daily_returns.iloc[-160:-80].sum()                  
        sum_90 = daily_returns.iloc[-250:-160].sum()                 
        
        total_score = sum_20 + sum_60 + sum_80 + sum_90
        
        results = pd.DataFrame({
            'Symbol': [t.replace('.NS', '') for t in total_score.index],
            'Last_20_Days': sum_20.values,
            'Days_20_to_80': sum_60.values,
            'Days_80_to_160': sum_80.values,
            'Days_160_to_250': sum_90.values,
            'Total_Score': total_score.values
        }).dropna()

        results = pd.merge(results, original_df[['Symbol', 'Stock Name', 'sector']], on='Symbol', how='left')
        
        # 4. Filter Top 40%
        results = results.sort_values(by='Total_Score', ascending=False).reset_index(drop=True)
        top_40_count = max(1, int(len(results) * 0.40))
        top_40_df = results.head(top_40_count).copy()
        
        # 5. Categories
        green_cutoff = int(top_40_count * 0.33)
        gray_cutoff = int(top_40_count * 0.66)
        
        top_40_df['Category'] = 'Red'
        if green_cutoff > 0:
            top_40_df.iloc[:green_cutoff, top_40_df.columns.get_loc('Category')] = 'Green'     
            top_40_df.iloc[green_cutoff:gray_cutoff, top_40_df.columns.get_loc('Category')] = 'Gray' 
            
        # 🔗 NEW: Create Clickable TradingView URL column
        top_40_df['TradingView_Link'] = "https://in.tradingview.com/chart/?symbol=NSE:" + top_40_df['Symbol']
            
        cols = ['Stock Name', 'TradingView_Link', 'sector', 'Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250', 'Category', 'Symbol']
        top_40_df = top_40_df[[c for c in cols if c in top_40_df.columns]]
        
        num_cols = ['Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250']
        top_40_df[num_cols] = top_40_df[num_cols].round(2)
        
        st.success(f"Scan Complete! Displaying Top 40% ({top_40_count} Stocks). Click on any Symbol to open its chart.")
        
        # 6. Apply Colors
        def style_rows(row):
            if row['Category'] == 'Green':
                return ['background-color: #c3e6cb; color: black'] * len(row)
            elif row['Category'] == 'Gray':
                return ['background-color: #d6d8d9; color: black'] * len(row)
            elif row['Category'] == 'Red':
                return ['background-color: #f5c6cb; color: black'] * len(row)
            return [''] * len(row)
            
        # 7. Display table with clickable links
        st.dataframe(
            top_40_df.style.apply(style_rows, axis=1), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "TradingView_Link": st.column_config.LinkColumn(
                    "Symbol", # Displays 'Symbol' as header
                    display_text=r"https://in\.tradingview\.com/chart/\?symbol=NSE:(.*)" # Extracts text after 'NSE:' to show clean symbol names
                ),
                "Symbol": None # Hides duplicate plain text symbol from web UI
            }
        )
        
        # Download Button
        csv = top_40_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name='momentum_scan_results.csv',
            mime='text/csv',
        )
