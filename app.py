import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import os

st.set_page_config(page_title="NSE Sector Leaders Scanner", layout="wide")
st.title("📊 NSE Sector-wise Momentum Scanner")

st.markdown("""
**📝 Instructions:**
Click the button below to start scanning. The app will automatically read the `sector leaders scanner csv.csv` file from the repository, calculate momentum for all 1900+ stocks, and classify the Top 10% sector leaders.
""")

@st.cache_data(ttl=7200) # 2 ghante tak data cache karega
def fetch_and_calculate_scores(df_input):
    cols = {c.strip().lower(): c for c in df_input.columns}
    sym_col = cols.get('symbol')
    sec_col = cols.get('sector')
    
    if not sym_col or not sec_col:
        return None, "❌ CSV file mein 'Symbol' aur 'sector' columns nahi mile."
        
    stock_map = {}
    for sym, sec in zip(df_input[sym_col], df_input[sec_col]):
        if pd.isna(sym) or pd.isna(sec): 
            continue
        clean_sym = str(sym).strip().upper().replace('.NS', '')
        stock_map[clean_sym] = str(sec).strip()
        
    tickers = [f"{ticker}.NS" for ticker in stock_map.keys()]
    
    # Batch download
    data = yf.download(tickers, period="1y", group_by='ticker', threads=True)
    
    results = []
    progress_bar = st.progress(0)
    total_tickers = len(tickers)
    
    for idx, ticker_symbol in enumerate(tickers):
        base_ticker = ticker_symbol.replace('.NS', '')
        sector = stock_map[base_ticker]
        
        try:
            if len(tickers) == 1:
                df = data.copy()
            else:
                if ticker_symbol not in data:
                    continue
                df = data[ticker_symbol].copy()
                
            df.dropna(subset=['Close'], inplace=True)
            
            # Require at least 250 trading days
            if len(df) < 250:
                continue 
                
            df['Return'] = df['Close'].pct_change() * 100
            
            sum_20 = df['Return'].iloc[-20:].sum()
            sum_60 = df['Return'].iloc[-80:-20].sum()
            sum_80 = df['Return'].iloc[-160:-80].sum()
            sum_90 = df['Return'].iloc[-250:-160].sum()
            
            total_score = sum_20 + sum_60 + sum_80 + sum_90
            
            results.append({
                'Stock': base_ticker,
                'Sector': sector,
                'Score': total_score,
                'Last_20D': round(sum_20, 2),
                'Days_21_80': round(sum_60, 2),
                'Days_81_160': round(sum_80, 2),
                'Days_161_250': round(sum_90, 2)
            })
            
        except Exception:
            pass 
            
        if idx % 10 == 0:
            progress_bar.progress((idx + 1) / total_tickers)
            
    progress_bar.empty()
    return pd.DataFrame(results), None

def apply_color(val):
    if val == 'Top 33% (Green)':
        return 'background-color: #198754; color: white;' 
    elif val == 'Middle 33% (Gray)':
        return 'background-color: #6c757d; color: white;' 
    elif val == 'Bottom 34% (Red)':
        return 'background-color: #dc3545; color: white;' 
    return ''

# Check if file exists in the GitHub repo directory
file_name = "sector leaders scanner csv.csv"

if os.path.exists(file_name):
    st.success(f"✅ File '{file_name}' successfully loaded from server.")
    
    if st.button("🚀 Run Stock Scanner"):
        try:
            df_input = pd.read_csv(file_name)
            st.info(f"⏳ Fetching 1-year data for {len(df_input)} stocks... (This may take 2-4 minutes).")
            
            df_scores, error_msg = fetch_and_calculate_scores(df_input)
            
            if error_msg:
                st.error(error_msg)
            elif df_scores is not None and not df_scores.empty:
                top_stocks_list = []
                
                for sector, group in df_scores.groupby('Sector'):
                    if len(group) == 0:
                        continue
                    threshold = group['Score'].quantile(0.90)
                    top_in_sector = group[group['Score'] >= threshold].copy()
                    top_stocks_list.append(top_in_sector)
                    
                if top_stocks_list:
                    final_df = pd.concat(top_stocks_list)
                    
                    final_df['Percentile'] = final_df['Score'].rank(pct=True)
                    
                    conditions = [
                        (final_df['Percentile'] >= 0.67),
                        (final_df['Percentile'] >= 0.34) & (final_df['Percentile'] < 0.67),
                        (final_df['Percentile'] < 0.34)
                    ]
                    choices = ['Top 33% (Green)', 'Middle 33% (Gray)', 'Bottom 34% (Red)']
                    final_df['Category'] = np.select(conditions, choices, default='Bottom 34% (Red)')
                    
                    final_df = final_df.sort_values(by=['Score'], ascending=False).drop(columns=['Percentile'])
                    final_df.reset_index(drop=True, inplace=True)
                    
                    # 🟢 NAYA ADD KIYA GAYA HISA: TradingView Link Column
                    # Stock column ke just baad (Index 1) TradingView link insert karna
                    final_df.insert(1, 'TradingView', "https://in.tradingview.com/chart/?symbol=NSE:" + final_df['Stock'])
                    
                    st.success(f"✅ Scanning Complete! Found {len(final_df)} Top 10% sector leaders.")
                    st.subheader("🏆 Classified Stock Leaders")
                    
                    styled_df = final_df.style.map(apply_color, subset=['Category']).format({
                        "Score": "{:.2f}", "Last_20D": "{:.2f}", "Days_21_80": "{:.2f}", 
                        "Days_81_160": "{:.2f}", "Days_161_250": "{:.2f}"
                    })
                    
                    # 🟢 st.dataframe mein column_config use karke text ko clickable link banana
                    st.dataframe(
                        styled_df, 
                        height=600, 
                        use_container_width=True,
                        column_config={
                            "TradingView": st.column_config.LinkColumn(
                                "TradingView",
                                help="Click to open chart on TradingView",
                                display_text="📊 View Chart"
                            )
                        }
                    )
                    
                    # CSV Download karne se pehle TradingView column ko hata dena taaki CSV clean rahe
                    download_df = final_df.drop(columns=['TradingView'])
                    csv_export = download_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="⬇️ Download Final Results CSV",
                        data=csv_export,
                        file_name="Categorized_Sector_Leaders.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("Data process hone ke baad top 10% criteria mein koi stock match nahi hua.")
            else:
                st.error("❌ Valid stocks ka data fetch nahi ho paya. Please internet connection check karein.")
                
        except Exception as e:
            st.error(f"Error processing file: {e}")
else:
    st.error(f"❌ '{file_name}' GitHub repository mein nahi mili. Kripya ensure karein ki CSV file aur app.py ek hi folder mein hain.")
