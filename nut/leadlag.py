"""Lead-lag tests on weekly log changes, using only numpy.

Granger-style F test: does adding p lags of x to an AR(p) model of y reduce the residual sum of squares?
The p-value comes from circular shifts of x (every shift of at least `min_shift` weeks), which keeps the
autocorrelation of both series and breaks only their alignment. No distributional assumptions, no scipy.
"""
from __future__ import annotations

import numpy as np


def _lagged(v: np.ndarray, p: int) -> np.ndarray:
    n = len(v)
    return np.column_stack([v[p - i : n - i] for i in range(1, p + 1)])


def _rss(X: np.ndarray, Y: np.ndarray) -> float:
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    r = Y - X @ beta
    return float(r @ r)


def granger_f(y: np.ndarray, x: np.ndarray, p: int) -> tuple[float, float]:
    """Return (F statistic, gain in R^2) for 'x Granger-causes y' with p lags."""
    Y = y[p:]
    ones = np.ones((len(Y), 1))
    Xr = np.hstack([ones, _lagged(y, p)])
    Xu = np.hstack([Xr, _lagged(x, p)])
    rss_r, rss_u = _rss(Xr, Y), _rss(Xu, Y)
    df2 = len(Y) - Xu.shape[1]
    f = ((rss_r - rss_u) / p) / (rss_u / df2)
    tss = float(((Y - Y.mean()) ** 2).sum())
    return f, (rss_r - rss_u) / tss


def shift_pvalue(y: np.ndarray, x: np.ndarray, p: int, min_shift: int) -> dict:
    f0, gain = granger_f(y, x, p)
    n = len(x)
    shifts = list(range(min_shift, n - min_shift + 1))
    null = np.array([granger_f(y, np.roll(x, s), p)[0] for s in shifts])
    pval = (1 + int((null >= f0).sum())) / (1 + len(null))
    return {"f": f0, "r2_gain": gain, "p_value": pval, "n_obs": n - p, "n_shifts": len(null)}


def xcorr(y: np.ndarray, x: np.ndarray, max_lag: int, min_shift: int) -> dict:
    """corr(x[t-k], y[t]) for k in [-max_lag, max_lag]; k>0 means x leads y.

    Null band: 95th percentile of |corr| over all circular shifts >= min_shift, pooled over lags.
    """
    def corr_at(xx, k):
        if k > 0:
            a, b = xx[:-k], y[k:]
        elif k < 0:
            a, b = xx[-k:], y[:k]
        else:
            a, b = xx, y
        return float(np.corrcoef(a, b)[0, 1])

    lags = list(range(-max_lag, max_lag + 1))
    obs = [corr_at(x, k) for k in lags]
    n = len(x)
    pooled = [abs(corr_at(np.roll(x, s), k)) for s in range(min_shift, n - min_shift + 1) for k in lags]
    band = float(np.quantile(pooled, 0.95))
    return {"lags": lags, "corr": obs, "band95": band}


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        val = min(1.0, (m - rank) * pvals[idx])
        running = max(running, val)
        adj[idx] = running
    return adj.tolist()
