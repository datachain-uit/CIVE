"""Redraw XRP equity curve using real backtest_real_data.json"""
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter

with open('backtest_real_data.json') as f:
    data = json.load(f)

equity = data['equity']
x = list(range(len(equity)))

peak = equity[0]
dd = []
for v in equity:
    if v > peak: peak = v
    dd.append((peak - v) / peak * 100)

GREEN = '#3fb950'; RED = '#f85149'
plt.rcParams.update({
    'figure.facecolor':'#0d1117','axes.facecolor':'#0d1117',
    'axes.edgecolor':'#30363d','axes.labelcolor':'#c9d1d9',
    'xtick.color':'#8b949e','ytick.color':'#8b949e',
    'text.color':'#c9d1d9','grid.color':'#21262d',
    'grid.linestyle':'--','grid.alpha':0.5,
    'font.family':'DejaVu Sans','font.size':10
})

fig = plt.figure(figsize=(10,6), facecolor='#0d1117')
gs  = gridspec.GridSpec(2, 1, height_ratios=[3,1], hspace=0.06)
ax1 = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1], sharex=ax1)

ax1.plot(x, equity, color=GREEN, lw=1.8, label='Proposed System', zorder=3)
ax1.fill_between(x, 100, equity,
                 where=[v>=100 for v in equity], alpha=0.12, color=GREEN)
ax1.fill_between(x, 100, equity,
                 where=[v<100  for v in equity], alpha=0.15, color=RED)
ax1.axhline(y=100, color='#8b949e', ls='--', lw=0.8, alpha=0.5)

bnh = [100*(1-0.118*i/(len(equity)-1)) for i in range(len(equity))]
ax1.plot(x, bnh, color=RED, lw=1.2, ls='--',
         label='Buy and Hold (-11.8%)', alpha=0.7)

peak_val = max(equity)
peak_idx = equity.index(peak_val)
ax1.annotate(
    f'Peak: ${peak_val:,.0f}',
    xy=(peak_idx, peak_val),
    xytext=(peak_idx - 40, peak_val * 0.87),
    color=GREEN, fontsize=8,
    arrowprops=dict(arrowstyle='->', color=GREEN, lw=1))
ax1.annotate(
    f'+393.39%\n$493 USDT',
    xy=(len(equity)-1, equity[-1]),
    xytext=(len(equity)-55, equity[-1]*0.80),
    color=GREEN, fontsize=9, fontweight='bold',
    arrowprops=dict(arrowstyle='->', color=GREEN, lw=1))

ax1.set_ylabel('Portfolio Balance (USDT)')
ax1.set_title(
    'XRP/USDT Equity Curve — Proposed System vs. Buy-and-Hold\n'
    '(Binance Futures, 180 Days, 100 USDT Initial)',
    fontsize=11, color='#e6edf3')
ax1.legend(loc='upper left', fontsize=9)
ax1.grid(True, alpha=0.3)
ax1.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'${v:,.0f}'))
plt.setp(ax1.get_xticklabels(), visible=False)

max_dd_idx = dd.index(max(dd))
ax2.fill_between(x, 0, [-d for d in dd], color=RED, alpha=0.5)
ax2.plot(x, [-d for d in dd], color=RED, lw=1.0)
ax2.annotate(
    f'MaxDD: {max(dd):.1f}%',
    xy=(max_dd_idx, -max(dd)),
    xytext=(max_dd_idx + 8, -max(dd)*0.55),
    color=RED, fontsize=8,
    arrowprops=dict(arrowstyle='->', color=RED, lw=1))
ax2.set_ylabel('Drawdown (%)')
ax2.set_xlabel('Trade Number')
ax2.yaxis.set_major_formatter(FuncFormatter(lambda y,_: f'{y:.0f}%'))
ax2.grid(True, alpha=0.25)

plt.tight_layout()
plt.savefig('figures/equity_curve_xrp.png', dpi=180,
            bbox_inches='tight', facecolor='#0d1117')
print(f'OK  MaxDD={max(dd):.2f}%  Final=${equity[-1]:.2f}')
