import pandas as pd

def add_rsi(df, length=14):
    delta = df['Close'].diff()
    # match standard RMA calculation used by pandas-ta and TradingView
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    
    alpha = 1 / length
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    df[f'RSI_{length}'] = 100 - (100 / (1 + rs))
    return df

def add_bbands(df, length=20, std=2.0):
    sma = df['Close'].rolling(window=length).mean()
    rolling_std = df['Close'].rolling(window=length).std(ddof=0)
    df[f'BBU_{length}_{std}_{std}'] = sma + (rolling_std * std)
    df[f'BBL_{length}_{std}_{std}'] = sma - (rolling_std * std)
    return df

def add_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - signal_line
    df[f'MACDh_{fast}_{slow}_{signal}'] = macd_hist
    return df
