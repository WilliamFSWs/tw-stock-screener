import pandas as pd
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('data/stock_ev_report.csv')
print('=== 各模式整體平均勝率與期望值 ===')
summary = df.groupby('Pattern').agg(
    Avg_Win_Rate=('Win_Rate(%)', 'mean'),
    Avg_EV=('Expected_Value(%)', 'mean'),
    Total_Signals=('Signals', 'sum'),
    Avg_Drawdown=('Max_Drawdown(%)', 'mean')
).sort_values('Avg_Win_Rate', ascending=False)
print(summary.round(2))

print('\n=== 訊號觸發次數與勝率的關係 ===')
# Only look at signals that appeared enough times
bins = [0, 5, 15, 30, 50, 100, 1000]
df['Signal_Bin'] = pd.cut(df['Signals'], bins)
signal_perf = df.groupby('Signal_Bin').agg(
    Avg_Win_Rate=('Win_Rate(%)', 'mean'), 
    Count=('Stock_ID', 'count')
)
print(signal_perf.round(2))

print('\n=== 最大跌幅(洗盤深度)與勝率的關係 ===')
dd_bins = [-100, -20, -15, -10, -5, 0]
df['DD_Bin'] = pd.cut(df['Max_Drawdown(%)'], dd_bins)
dd_perf = df.groupby('DD_Bin').agg(
    Avg_Win_Rate=('Win_Rate(%)', 'mean'), 
    Avg_Return=('Avg_Return(%)', 'mean'),
    Count=('Stock_ID', 'count')
)
print(dd_perf.round(2))
