import json
import argparse
import numpy as np
import scipy.stats as stats
import pandas as pd
from datetime import datetime
from pathlib import Path

def jobson_korkie_test(returns_a, returns_b):
    """
    Jobson-Korkie test for the equality of two Sharpe Ratios.
    Returns the Z-statistic and p-value.
    """
    if len(returns_a) < 2 or len(returns_b) < 2:
        return np.nan, np.nan
        
    mu_a = np.mean(returns_a)
    mu_b = np.mean(returns_b)
    
    var_a = np.var(returns_a, ddof=1)
    var_b = np.var(returns_b, ddof=1)
    
    cov_ab = np.cov(returns_a, returns_b)[0, 1]
    
    T = len(returns_a)
    
    # Calculate Sharpe Ratios
    sh_a = mu_a / np.sqrt(var_a) if var_a > 0 else 0
    sh_b = mu_b / np.sqrt(var_b) if var_b > 0 else 0
    
    # Jobson-Korkie statistic
    theta = (1 / (T - 1)) * (
        2 * var_a**2 * var_b**2 
        - 2 * var_a * var_b * cov_ab 
        + 0.5 * mu_a**2 * var_b**2 
        + 0.5 * mu_b**2 * var_a**2 
        - (mu_a * mu_b / (var_a * var_b)) * cov_ab**2
    )
    
    if theta <= 0:
        return np.nan, np.nan
        
    z_stat = (sh_a - sh_b) / np.sqrt(theta)
    p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))
    
    return z_stat, p_value

def diebold_mariano_test(returns_baseline, returns_model):
    """
    Simplified Diebold-Mariano test comparing the returns of two models.
    Hypothesis: The predictive ability (returns) of 'model' is better than 'baseline'.
    """
    if len(returns_baseline) != len(returns_model):
        return np.nan, np.nan
        
    d = np.array(returns_model) - np.array(returns_baseline)
    mean_d = np.mean(d)
    var_d = np.var(d, ddof=1)
    
    if var_d == 0:
        return np.nan, np.nan
        
    T = len(d)
    dm_stat = mean_d / np.sqrt(var_d / T)
    p_value = stats.norm.sf(dm_stat) # 1-tailed test for superiority
    
    return dm_stat, p_value

def calculate_information_ratio(returns_baseline, returns_model):
    """
    Calculates the Information Ratio of the model relative to the baseline.
    IR = Mean(Active Return) / Tracking Error
    """
    active_returns = np.array(returns_model) - np.array(returns_baseline)
    mean_active_return = np.mean(active_returns)
    tracking_error = np.std(active_returns, ddof=1)
    
    if tracking_error == 0:
        return 0.0
        
    # Annualize (assuming daily returns)
    return (mean_active_return / tracking_error) * np.sqrt(365)


def convert_trades_to_daily_returns(trades_dict, valid_symbols, days=730):
    """
    Converts a dict of symbol -> list of trade dicts into a daily portfolio return series.
    Returns a pandas Series of daily portfolio returns.
    """
    all_trades = []
    for symbol, trades in trades_dict.items():
        if symbol in valid_symbols:
            for t in trades:
                t['symbol'] = symbol
                all_trades.append(t)
            
    if not all_trades:
        return pd.Series(np.zeros(days))
        
    df = pd.DataFrame(all_trades)
    df['date'] = pd.to_datetime(df['timestamp'], unit='s').dt.floor('D')
    
    # Calculate daily PnL
    daily_pnl = df.groupby('date')['pnl'].sum()
    
    # For a rigorous return calculation, we need daily portfolio equity.
    # To approximate, we start with 100 * len(valid_symbols) = N * 100 USDT total balance.
    starting_balance = 100.0 * len(valid_symbols)
    equity_curve = [starting_balance]
    returns = []
    
    # Create a continuous date range to fill missing days with 0 return
    start_date = daily_pnl.index.min()
    end_date = start_date + pd.Timedelta(days=days-1)
    date_range = pd.date_range(start_date, end_date)
    
    daily_pnl = daily_pnl.reindex(date_range, fill_value=0.0)
    
    for date, pnl in daily_pnl.items():
        daily_return = pnl / equity_curve[-1] if equity_curve[-1] > 0 else 0
        returns.append(daily_return)
        equity_curve.append(equity_curve[-1] + pnl)
        
    return pd.Series(returns, index=date_range)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True, help="Path to baseline trades JSON (e.g. vibe_trades.json)")
    parser.add_argument('--model', required=True, help="Path to model trades JSON (e.g. hybrid_trades.json)")
    parser.add_argument('--days', type=int, default=730)
    args = parser.parse_args()
    
    with open(args.baseline, 'r') as f:
        baseline_data = json.load(f)
        
    with open(args.model, 'r') as f:
        model_data = json.load(f)
        
    # Only evaluate on intersection of successfully backtested symbols
    valid_symbols = [
        sym for sym in baseline_data.keys()
        if len(baseline_data[sym]) > 0 and len(model_data.get(sym, [])) > 0
    ]
    print(f"Running stats on {len(valid_symbols)} common successful pairs: {valid_symbols}")
    
    ret_baseline = convert_trades_to_daily_returns(baseline_data, valid_symbols, args.days)
    ret_model = convert_trades_to_daily_returns(model_data, valid_symbols, args.days)
    
    # Align lengths just in case
    min_len = min(len(ret_baseline), len(ret_model))
    ret_b = ret_baseline.iloc[:min_len].values
    ret_m = ret_model.iloc[:min_len].values
    
    z_jk, p_jk = jobson_korkie_test(ret_b, ret_m)
    dm_stat, p_dm = diebold_mariano_test(ret_b, ret_m)
    info_ratio = calculate_information_ratio(ret_b, ret_m)
    
    results = {
        "Jobson_Korkie": {
            "Z_statistic": float(z_jk),
            "p_value": float(p_jk),
            "significant": bool(p_jk < 0.05)
        },
        "Diebold_Mariano": {
            "DM_statistic": float(dm_stat),
            "p_value": float(p_dm),
            "significant": bool(p_dm < 0.05)
        },
        "Information_Ratio": float(info_ratio)
    }
    
    print("\n=== STATISTICAL SIGNIFICANCE RESULTS ===")
    print(f"Jobson-Korkie Test for Sharpe Equality:")
    print(f"  Z-stat: {z_jk:.4f} | P-value: {p_jk:.4f} {'(Significant)' if p_jk < 0.05 else '(Not Significant)'}")
    print(f"Diebold-Mariano Test for Superior Predictive Ability:")
    print(f"  DM-stat: {dm_stat:.4f} | P-value: {p_dm:.4f} {'(Significant)' if p_dm < 0.05 else '(Not Significant)'}")
    print(f"Information Ratio (Active Return / Tracking Error):")
    print(f"  IR: {info_ratio:.4f}")
    
    with open('results/statistical_significance.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()
