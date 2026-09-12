"""
Hierarchical Risk Parity and CVaR allocation.

Uses Riskfolio-Lib's ``HCPortfolio`` when it is importable and falls back to
a native Lopez de Prado HRP (tree clustering, quasi-diagonalisation,
recursive bisection) with either variance or historical CVaR as the cluster
risk measure. Output weights are non-negative, clipped to [min, max] and sum
to one.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    def __init__(
        self,
        method: str = "HRP",
        risk_measure: str = "MV",  # "MV" (variance) or "CVaR"
        cvar_alpha: float = 0.05,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        linkage_method: str = "single",
        use_riskfolio: bool = True,
    ) -> None:
        if method not in ("HRP", "CVaR", "EQUAL"):
            raise ValueError("method must be HRP, CVaR or EQUAL")
        self.method = method
        self.risk_measure = "CVaR" if method == "CVaR" else risk_measure
        self.cvar_alpha = cvar_alpha
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.linkage_method = linkage_method
        self.use_riskfolio = use_riskfolio
        self.last_engine: Optional[str] = None

    # ---------------------------------------------------------------- public
    def optimize_weights(self, returns_df: pd.DataFrame) -> Dict[str, float]:
        if returns_df is None or returns_df.empty or returns_df.shape[1] == 0:
            return {}
        returns_df = returns_df.dropna(how="all").fillna(0.0)
        assets = list(returns_df.columns)
        if len(assets) == 1:
            self.last_engine = "single"
            return {assets[0]: 1.0}
        if self.method == "EQUAL" or len(returns_df) < 3:
            self.last_engine = "equal"
            return self._clip({a: 1.0 / len(assets) for a in assets})

        if self.use_riskfolio:
            try:
                import riskfolio as rp  # type: ignore

                port = rp.HCPortfolio(returns=returns_df)
                w = port.optimization(
                    model="HRP",
                    codependence="pearson",
                    rm=self.risk_measure,
                    rf=0.0,
                    linkage=self.linkage_method,
                    leaf_order=True,
                )
                self.last_engine = "riskfolio"
                return self._clip(w["weights"].to_dict())
            except ImportError:
                pass
            except Exception as exc:  # pragma: no cover - library specific
                logger.warning("Riskfolio HRP failed (%s); using native HRP.", exc)

        self.last_engine = "native"
        return self._clip(self._native_hrp(returns_df))

    # ---------------------------------------------------------------- native
    def _native_hrp(self, returns_df: pd.DataFrame) -> Dict[str, float]:
        assets = list(returns_df.columns)
        corr = returns_df.corr().fillna(0.0).to_numpy(copy=True)
        np.fill_diagonal(corr, 1.0)
        dist = np.sqrt(0.5 * (1.0 - np.clip(corr, -1.0, 1.0)))
        np.fill_diagonal(dist, 0.0)
        link = linkage(squareform(dist, checks=False), method=self.linkage_method)
        order = leaves_list(link)
        ordered = [assets[i] for i in order]

        weights = pd.Series(1.0, index=ordered)
        clusters = [ordered]
        while clusters:
            clusters = [
                c[j:k]
                for c in clusters
                for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                if len(c) > 1
            ]
            for i in range(0, len(clusters), 2):
                left, right = clusters[i], clusters[i + 1]
                var_l = self._cluster_risk(returns_df[left])
                var_r = self._cluster_risk(returns_df[right])
                denom = var_l + var_r
                alpha = 0.5 if denom <= 0 else 1.0 - var_l / denom
                weights[left] *= alpha
                weights[right] *= 1.0 - alpha
        total = weights.sum()
        if total > 0:
            weights /= total
        return weights.to_dict()

    def _cluster_risk(self, sub: pd.DataFrame) -> float:
        cov = sub.cov().values
        diag = np.diag(cov).copy()
        diag[diag <= 0] = 1e-12
        ivp = 1.0 / diag
        ivp /= ivp.sum()
        if self.risk_measure == "CVaR":
            port_ret = sub.values @ ivp
            cutoff = np.quantile(port_ret, self.cvar_alpha)
            tail = port_ret[port_ret <= cutoff]
            cvar = -float(tail.mean()) if len(tail) else 0.0
            return max(cvar, 1e-12)
        return float(ivp @ cov @ ivp)

    # ------------------------------------------------------------------ util
    def _clip(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Water-filling projection onto {sum w = 1, min <= w <= max}."""
        w = pd.Series(weights, dtype=float).clip(lower=0.0)
        n = len(w)
        if w.sum() <= 0:
            w[:] = 1.0 / n
        w /= w.sum()
        lo, hi = self.min_weight, self.max_weight
        if hi * n < 1.0 - 1e-12 or lo * n > 1.0 + 1e-12:
            return {k: 1.0 / n for k in w.index}  # bounds infeasible: equal weight
        fixed = pd.Series(False, index=w.index)
        for _ in range(n + 1):
            over = (w > hi + 1e-12) & ~fixed
            under = (w < lo - 1e-12) & ~fixed
            if not over.any() and not under.any():
                break
            w[over] = hi
            w[under] = lo
            fixed |= over | under
            free = ~fixed
            remaining = 1.0 - float(w[fixed].sum())
            if free.any():
                fs = float(w[free].sum())
                w[free] = w[free] / fs * remaining if fs > 0 else remaining / int(free.sum())
        return {k: float(v) for k, v in w.items()}
