"""
Robustez estadística: ¿el resultado es habilidad o suerte?  (numpy puro, sin scipy)

  * monte_carlo      remuestrea los trades miles de veces -> rango realista de retorno y de caída máxima.
  * psr              Probabilistic Sharpe Ratio: probabilidad de que el Sharpe verdadero supere un umbral,
                     corrigiendo por pocas muestras, asimetría y colas gordas (Bailey & López de Prado, 2012).
  * dsr              Deflated Sharpe Ratio: igual, pero descontando que se probaron N configuraciones
                     y se mostró la mejor (Bailey & López de Prado, 2014).
  * robustness       resumen listo para informes / panel.

Todo trabaja con retornos POR TRADE (fracción del capital, p. ej. `port_ret`), no anualizados: la
estadística de significancia solo depende de cuántas observaciones hay y de su forma.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def _clean(x) -> np.ndarray:
    a = np.asarray(x, dtype=float).ravel()
    return a[np.isfinite(a)]


def sharpe(x) -> float:
    """Sharpe por observación (media / desviación). 0 si no se puede calcular."""
    a = _clean(x)
    if len(a) < 3:
        return 0.0
    sd = a.std(ddof=1)
    return float(a.mean() / sd) if sd > 0 else 0.0


def _moments(a: np.ndarray) -> tuple[float, float]:
    """Asimetría y curtosis (no excesiva: normal = 3)."""
    sd = a.std(ddof=0)
    if sd == 0:
        return 0.0, 3.0
    z = (a - a.mean()) / sd
    return float((z ** 3).mean()), float((z ** 4).mean())


def psr(x, benchmark: float = 0.0) -> float:
    """P(Sharpe verdadero > benchmark). Con < 10 observaciones devuelve NaN (no hay base)."""
    a = _clean(x)
    n = len(a)
    if n < 10:
        return float("nan")
    sr = sharpe(a)
    skew, kurt = _moments(a)
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        return float("nan")
    return float(_N.cdf((sr - benchmark) * math.sqrt(n - 1) / math.sqrt(denom)))


def expected_max_sharpe(n_trials: int, sr_var: float) -> float:
    """Sharpe máximo esperado por puro azar entre `n_trials` estrategias sin edge (varianza `sr_var` entre ellas)."""
    if n_trials <= 1 or sr_var <= 0:
        return 0.0
    sd = math.sqrt(sr_var)
    return float(sd * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
                       + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e))))


def dsr(x, n_trials: int, sr_var: float | None = None) -> float:
    """PSR contra el umbral que se esperaría por azar tras probar `n_trials` configuraciones.
    Si no se conoce la varianza del Sharpe entre pruebas se usa la aproximación 1/(n-1) (nula)."""
    a = _clean(x)
    if len(a) < 10:
        return float("nan")
    var = sr_var if sr_var is not None else 1.0 / (len(a) - 1)
    return psr(a, benchmark=expected_max_sharpe(max(1, int(n_trials)), var))


def _max_drawdown(curves: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(curves, axis=1)
    return (curves / peak - 1.0).min(axis=1)


def monte_carlo(returns, n_sims: int = 5000, seed: int = 7, ruin_dd: float = -0.20,
                horizon: int | None = None) -> dict:
    """Remuestrea los retornos por trade (con reemplazo) `n_sims` veces.
    `horizon` = trades por simulación (por defecto, los mismos que la muestra).
    Devuelve percentiles de retorno final y caída máxima, y probabilidad de perder y de tocar `ruin_dd`.
    Limitación: asume trades independientes (no captura rachas de mercado)."""
    a = _clean(returns)
    if len(a) < 10:
        return {"n": int(len(a)), "ok": False}
    h = int(horizon or len(a))
    rng = np.random.default_rng(seed)
    draws = rng.choice(a, size=(n_sims, h), replace=True)
    curves = np.cumprod(1.0 + draws, axis=1)
    final = curves[:, -1] - 1.0
    dd = _max_drawdown(np.concatenate([np.ones((n_sims, 1)), curves], axis=1))
    q = lambda v, p: float(np.percentile(v, p))
    return {"ok": True, "n": int(len(a)), "horizon": h, "sims": int(n_sims),
            "ret_p5": q(final, 5), "ret_p50": q(final, 50), "ret_p95": q(final, 95),
            "dd_p50": q(dd, 50), "dd_p95": q(dd, 5),          # dd es negativo: el peor 5% está en el percentil 5
            "p_loss": float((final < 0).mean()), "p_ruin": float((dd <= ruin_dd).mean()), "ruin_dd": ruin_dd}


def bootstrap_sharpe_ci(returns, n: int = 3000, seed: int = 7) -> tuple[float, float]:
    """Intervalo de confianza 95% del Sharpe por trade (bootstrap)."""
    a = _clean(returns)
    if len(a) < 10:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    s = rng.choice(a, size=(n, len(a)), replace=True)
    sd = s.std(axis=1, ddof=1)
    sr = np.where(sd > 0, s.mean(axis=1) / np.where(sd > 0, sd, 1), 0.0)
    return float(np.percentile(sr, 2.5)), float(np.percentile(sr, 97.5))


def min_track_record(returns, benchmark: float = 0.0, confidence: float = 0.95) -> float:
    """Trades necesarios para que el Sharpe observado sea significativo al nivel `confidence` (MinTRL)."""
    a = _clean(returns)
    if len(a) < 10:
        return float("nan")
    sr = sharpe(a)
    if sr <= benchmark:
        return float("inf")
    skew, kurt = _moments(a)
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        return float("nan")
    return float(1 + denom * (_N.inv_cdf(confidence) / (sr - benchmark)) ** 2)


def robustness(returns, n_trials: int = 1, ruin_dd: float = -0.20, n_sims: int = 5000) -> dict:
    """Resumen: PSR, DSR, IC del Sharpe, Monte Carlo y trades mínimos para que sea concluyente."""
    a = _clean(returns)
    out = {"n": int(len(a)), "n_trials": int(n_trials), "sharpe_trade": sharpe(a)}
    if len(a) < 10:
        out["enough"] = False
        out["note"] = "Menos de 10 trades: no hay base estadística."
        return out
    lo, hi = bootstrap_sharpe_ci(a)
    out.update({"enough": True, "psr": psr(a), "dsr": dsr(a, n_trials), "sharpe_ci95": [lo, hi],
                "min_trades_95": min_track_record(a), "mc": monte_carlo(a, n_sims=n_sims, ruin_dd=ruin_dd)})
    return out


def verdict(r: dict) -> str:
    """Frase honesta a partir de `robustness()`."""
    if not r.get("enough"):
        return "Muestra insuficiente para juzgar (menos de 10 trades)."
    psr_, dsr_ = r["psr"], r["dsr"]
    if dsr_ == dsr_ and dsr_ >= 0.95:
        return f"Edge estadísticamente sólido incluso descontando {r['n_trials']} pruebas (DSR {dsr_:.0%})."
    if psr_ == psr_ and psr_ >= 0.95:
        return (f"Edge significativo (PSR {psr_:.0%}), pero NO sobrevive a descontar {r['n_trials']} pruebas "
                f"(DSR {dsr_:.0%}): puede ser selección de la mejor.")
    if psr_ == psr_ and psr_ >= 0.80:
        return f"Indicio de edge (PSR {psr_:.0%}) sin confirmar: hacen falta ~{r['min_trades_95']:.0f} trades."
    return f"Sin evidencia de edge (PSR {psr_:.0%}): indistinguible de suerte con {r['n']} trades."
