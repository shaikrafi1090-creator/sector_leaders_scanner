import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Custom Momentum Screener", layout="wide")
st.title("📈 Sector Leaders Momentum Screener (With Strict Filters)")

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

max_lookback_days = st.slider("Max historical days to check for 'Days at Position':", min_value=1, max_value=20, value=5)

if st.button("Run Scanner 🚀"):
    if not tickers:
        st.stop()
        
    with st.spinner("Downloading Data & Calculating... Isme thoda time lagega."):
        limit = 50 if "50 " in scan_mode else (500 if "500" in scan_mode else len(tickers))
        scan_tickers = tickers[:limit]
        
        # Data download
        data = yf.download(scan_tickers, period="18mo", group_by='ticker', threads=True, progress=False)
        
        close_prices = pd.DataFrame()
        open_prices = pd.DataFrame()
        high_prices = pd.DataFrame()
        low_prices = pd.DataFrame()
        
        # Ab Open, Close ke sath High aur Low bhi nikalenge
        if len(scan_tickers) == 1:
            close_prices[scan_tickers[0]] = data['Close']
            open_prices[scan_tickers[0]] = data['Open']
            high_prices[scan_tickers[0]] = data['High']
            low_prices[scan_tickers[0]] = data['Low']
        else:
            for ticker in scan_tickers:
                if ticker in data and 'Close' in data[ticker]:
                    close_prices[ticker] = data[ticker]['Close']
                    open_prices[ticker] = data[ticker]['Open']
                    high_prices[ticker] = data[ticker]['High']
                    low_prices[ticker] = data[ticker]['Low']
                    
        close_prices.dropna(axis=1, how='all', inplace=True)
        open_prices.dropna(axis=1, how='all', inplace=True)
        high_prices.dropna(axis=1, how='all', inplace=True)
        low_prices.dropna(axis=1, how='all', inplace=True)
        
        prev_close = close_prices.shift(1)
        
        # 🛑 FILTER 1: > 20% Gap Up in last 260 trading days
        gap_up_pct = ((open_prices - prev_close) / prev_close) * 100
        recent_gap_up = gap_up_pct.iloc[-260:]
        max_gap = recent_gap_up.max()
        valid_gap_tickers = max_gap[max_gap <= 20].index.tolist()
        
        # 🛑 FILTER 2: > 10 Circuits in last 260 trading days
        recent_close = close_prices.iloc[-260:]
        recent_high = high_prices.iloc[-260:]
        recent_low = low_prices.iloc[-260:]
        recent_prev_close = prev_close.iloc[-260:]
        
        recent_pct_change = ((recent_close - recent_prev_close) / recent_prev_close) * 100
        
        # Circuit Logic (0.02 is tolerance for float price values)
        upper_circuit = (recent_pct_change >= 4.9) & ((recent_high - recent_close) <= 0.02)
        lower_circuit = (recent_pct_change <= -4.9) & ((recent_close - recent_low) <= 0.02)
        locked_circuit = (recent_high - recent_low) <= 0.02
        
        is_circuit_day = upper_circuit | lower_circuit | locked_circuit
        circuit_counts = is_circuit_day.sum()
        
        valid_circuit_tickers = circuit_counts[circuit_counts <= 10].index.tolist()
        
        # Combine both valid lists (Dono filters pass karne wale stocks)
        final_valid_tickers = list(set(valid_gap_tickers) & set(valid_circuit_tickers))
        
        dropped_by_gap = len(max_gap) - len(valid_gap_tickers)
        dropped_by_circuit = len(circuit_counts) - len(valid_circuit_tickers)
        
        close_prices = close_prices[final_valid_tickers] # Apply final filter
        
        if dropped_by_gap > 0 or dropped_by_circuit > 0:
            st.warning(f"⚠️ **Filters Applied:** {dropped_by_gap} stocks rejected (Gap-up > 20%) | {dropped_by_circuit} stocks rejected (Circuits > 10).")

        # -------------------------------------------------------------
        # 🔗 Ranking Logic (Applied only on Valid Stocks)
        def get_ranks_for_day(prices_df, days_ago):
            end_idx = len(prices_df) - days_ago
            
            if end_idx < 250:
                return pd.Series(dtype=float)
                
            hist_prices = prices_df.iloc[:end_idx]
            daily_ret = hist_prices.pct_change() * 100
            
            s_20 = daily_ret.iloc[-20:].sum()
            s_60 = daily_ret.iloc[-80:-20].sum()
            s_80 = daily_ret.iloc[-160:-80].sum()
            s_90 = daily_ret.iloc[-250:-160].sum()
            
            tot_score = s_20 + s_60 + s_80 + s_90
            ranks = tot_score.rank(ascending=False, method='min')
            return ranks, s_20, s_60, s_80, s_90, tot_score

        current_ranks, sum_20, sum_60, sum_80, sum_90, total_score = get_ranks_for_day(close_prices, 0)
        
        historical_ranks_df = pd.DataFrame()
        historical_ranks_df['Day_0'] = current_ranks
        
        for i in range(1, max_lookback_days + 1):
            hist_rank, _, _, _, _, _ = get_ranks_for_day(close_prices, i)
            historical_ranks_df[f'Day_{i}'] = hist_rank
            
        days_at_position_list = []
        for stock in current_ranks.index:
            curr_rank = current_ranks[stock]
            days = 1 
            for i in range(1, max_lookback_days + 1):
                col_name = f'Day_{i}'
                if stock in historical_ranks_df.index and not pd.isna(historical_ranks_df.at[stock, col_name]) and historical_ranks_df.at[stock, col_name] == curr_rank:
                    days += 1
                else:
                    break 
            days_at_position_list.append(days)
            
        # Create Results DataFrame
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

        # Merge with original CSV
        results = pd.merge(results, original_df[['Symbol', 'Stock Name', 'sector']], on='Symbol', how='left')
        
        # Sort & Category
        results = results.sort_values(by='Current_Rank', ascending=True).reset_index(drop=True)
        top_40_count = max(1, int(len(results) * 0.40))
        top_40_df = results.head(top_40_count).copy()
        
        green_cutoff = int(top_40_count * 0.33)
        gray_cutoff = int(top_40_count * 0.66)
        
        top_40_df['Category'] = 'Red'
        if green_cutoff > 0:
            top_40_df.iloc[:green_cutoff, top_40_df.columns.get_loc('Category')] = 'Green'     
            top_40_df.iloc[green_cutoff:gray_cutoff, top_40_df.columns.get_loc('Category')] = 'Gray' 
            
        # Add URLs and Columns
        top_40_df['TradingView_Link'] = "https://in.tradingview.com/chart/?symbol=NSE:" + top_40_df['Symbol']
        cols = ['Current_Rank', 'Days_at_Position', 'Stock Name', 'TradingView_Link', 'sector', 'Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250', 'Category', 'Symbol']
        top_40_df = top_40_df[[c for c in cols if c in top_40_df.columns]]
        
        top_40_df['Current_Rank'] = top_40_df['Current_Rank'].astype(int)
        num_cols = ['Total_Score', 'Last_20_Days', 'Days_20_to_80', 'Days_80_to_160', 'Days_160_to_250']
        top_40_df[num_cols] = top_40_df[num_cols].round(2)
        
        st.success(f"✅ Scan Complete! Top 40% valid stocks displayed.")
        
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
                "TradingView_Link": st.column_config.LinkColumn("Symbol", display_text=r"https://in\.tradingview\.com/chart/\?symbol=NSE:(.*)"),
                "Symbol": None,
                "Days_at_Position": st.column_config.NumberColumn("Days at Position", format="%d")
            }
        )
        
        csv = top_40_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Download Results as CSV", data=csv, file_name='momentum_scan_results.csv', mime='text/csv')
