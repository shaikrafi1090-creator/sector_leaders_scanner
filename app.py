import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Custom Momentum Screener", layout="wide")
st.title("📈 Sector Leaders Momentum Screener")

# 1. Read stocks from CSV
@st.cache_data(ttl=86400)
def load_tickers_from_csv():
    try:
        df = pd.read_csv("sector leaders scanner csv.csv")
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        tickers = (df['Symbol'] + ".NS").tolist()
        return tickers, df
    except FileNotFoundError:
        st.error("Error: 'sector leaders scanner csv.csv' file not found.")
        return [], pd.DataFrame()

tickers, original_df = load_tickers_from_csv()
st.write(f"📂 Found **{len(tickers)}** stocks in **sector leaders scanner csv.csv**.")

scan_mode = st.selectbox(
    "Select Stock Universe (Kitne stocks scan karne hain?):", 
    ["Top 50 Stocks (Fast Test - 1 min)", "Top 500 Stocks (Medium - 3 mins)", "All 1900+ Stocks (Takes 10+ mins)"]
)

# Naya option: Kitne din tak check karna hai ki stock us position par hai
max_lookback_days = st.slider("Max historical days to check for 'Days at Position':", min_value=1, max_value=20, value=5)

if st.button("Run Scanner 🚀"):
    if not tickers:
        st.stop()
        
    with st.spinner("Downloading Data & Calculating... Isme thoda time lagega (Historical ranks calculating)."):
        limit = 50 if "50 " in scan_mode else (500 if "500" in scan_mode else len(tickers))
        scan_tickers = tickers[:limit]
        
        # Thoda zyada data download karenge kyunki past days ka bhi 250 din ka lookback chahiye
        # For current day + 20 days lookback = roughly 280-300 trading days needed. We use 1.5 years just to be safe.
        data = yf.download(scan_tickers, period="18mo", group_by='ticker', threads=True, progress=False)
        
        close_prices = pd.DataFrame()
        if len(scan_tickers) == 1:
            close_prices[scan_tickers[0]] = data['Close']
        else:
            for ticker in scan_tickers:
                if ticker in data and 'Close' in data[ticker]:
                    close_prices[ticker] = data[ticker]['Close']
                    
        close_prices.dropna(axis=1, how='all', inplace=True)
        
        # 🔗 NEW FUNCTION: Kisi specific din (offset) ka Rank nikalne ke liye
        def get_ranks_for_day(prices_df, days_ago):
            # End index calculation
            end_idx = len(prices_df) - days_ago
            
            # Agar data kam hai (250 din se kam)
            if end_idx < 250:
                return pd.Series(dtype=float)
                
            hist_prices = prices_df.iloc[:end_idx]
            daily_ret = hist_prices.pct_change() * 100
            
            # Aapka formula
            s_20 = daily_ret.iloc[-20:].sum()
            s_60 = daily_ret.iloc[-80:-20].sum()
            s_80 = daily_ret.iloc[-160:-80].sum()
            s_90 = daily_ret.iloc[-250:-160].sum()
            
            tot_score = s_20 + s_60 + s_80 + s_90
            # Rank based on score (1 is highest score)
            ranks = tot_score.rank(ascending=False, method='min')
            return ranks, s_20, s_60, s_80, s_90, tot_score

        # Get Current Day (Day 0) data
        current_ranks, sum_20, sum_60, sum_80, sum_90, total_score = get_ranks_for_day(close_prices, 0)
        
        # Calculate historical ranks (Pichle X dino tak)
        historical_ranks_df = pd.DataFrame()
        historical_ranks_df['Day_0'] = current_ranks
        
        for i in range(1, max_lookback_days + 1):
            hist_rank, _, _, _, _, _ = get_ranks_for_day(close_prices, i)
            historical_ranks_df[f'Day_{i}'] = hist_rank
            
        # Calculate 'Days at Position'
        days_at_position_list = []
        
        for stock in current_ranks.index:
            curr_rank = current_ranks[stock]
            days = 1 # Today
            
            for i in range(1, max_lookback_days + 1):
                col_name = f'Day_{i}'
                # Agar stock pichle din me tha aur uski rank same thi
                if stock in historical_ranks_df.index and not pd.isna(historical_ranks_df.at[stock, col_name]) and historical_ranks_df.at[stock, col_name] == curr_rank:
                    days += 1
                else:
                    break # Rank change ho gayi, break loop
            days_at_position_list.append(days)
            
        # Create Results
        results = pd.DataFrame({
            'Symbol': [t.replace('.NS', '') for t in total_score.index],
            'Current_Rank': current_ranks.values,
            'Days_at_Position': days_at_position_list,
            'Total_Score': total_score.values,
            'Last_20_Days': sum_20.values,
            'Days_20_to_80': sum_60.values,
            'Days_80_to_160': sum_80.values,
            'Days_160_to_250': sum_90.values
        }).dropna()

        # Merge with CSV
        results = pd.merge(results, original_df[['Symbol', 'Stock Name', 'sector']], on='Symbol', how='left')
        
        # Sort Top 40% based on Score (or Current Rank)
        results = results.sort_values(by='Current_Rank', ascending=True).reset_index(drop=True)
        top_40_count = max(1, int(len(results) * 0.40))
        top_40_df = results.head(top_40_count).copy()
        
        # Categories
        green_cutoff = int(top_40_count * 0.33)
        gray_cutoff = int(top_40_count * 0.66)
        
        top_40_df['Category'] = 'Red'
        if green_cutoff > 0:
            top_40_df.iloc[:green_cutoff, top_40_df.columns.get_loc('Category')] = 'Green'     
            top_40_df.iloc[green_cutoff:gray_cutoff, top_40_df.columns.get_loc('Category')] = 'Gray' 
            
        # URL 
        top_40_df['TradingView_Link'] = "https://in.tradingview.com/chart/?symbol=NSE:" + top_40_df['Symbol']
            
        # Organize columns - Rank aur Days ko pehle la diya hai
        cols = ['Current_Rank', 'Days_at_Position', 'Stock Name', 'TradingView_Link', 'sector', 'Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250', 'Category', 'Symbol']
        top_40_df = top_40_df[[c for c in cols if c in top_40_df.columns]]
        
        # Remove decimals from Rank and Days, format floats
        top_40_df['Current_Rank'] = top_40_df['Current_Rank'].astype(int)
        
        num_cols = ['Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250']
        top_40_df[num_cols] = top_40_df[num_cols].round(2)
        
        st.success(f"Scan Complete! Rank and 'Days at Position' updated.")
        
        # Colors
        def style_rows(row):
            if row['Category'] == 'Green':
                return ['background-color: #c3e6cb; color: black'] * len(row)
            elif row['Category'] == 'Gray':
                return ['background-color: #d6d8d9; color: black'] * len(row)
            elif row['Category'] == 'Red':
                return ['background-color: #f5c6cb; color: black'] * len(row)
            return [''] * len(row)
            
        st.dataframe(
            top_40_df.style.apply(style_rows, axis=1), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "TradingView_Link": st.column_config.LinkColumn(
                    "Symbol",
                    display_text=r"https://in\.tradingview\.com/chart/\?symbol=NSE:(.*)" 
                ),
                "Symbol": None,
                "Days_at_Position": st.column_config.NumberColumn(
                    "Days at Position (Rank)",
                    help="Kitne trading days se ye stock apni is current rank par tikkha hai",
                    format="%d"
                )
            }
        )
        
        # Download
        csv = top_40_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Download Results as CSV", data=csv, file_name='momentum_scan_results.csv', mime='text/csv')
