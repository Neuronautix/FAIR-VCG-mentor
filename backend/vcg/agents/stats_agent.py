import io
import base64
import warnings as _warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict, List, Any

_warnings.filterwarnings('ignore')

# Try to import statsmodels for power analysis
try:
    from statsmodels.stats.power import TTestIndPower
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

# Try pingouin for effect sizes
try:
    import pingouin as pg
    HAS_PINGOUIN = True
except ImportError:
    HAS_PINGOUIN = False


class StatsAgent:
    """Computes all statistical diagnostics for the generated VCG."""

    def run(
        self,
        real_control_df: pd.DataFrame,
        vcg_df: pd.DataFrame,
        outcome_cols: List[str],
        covariate_cols: List[str],
        confidence_level: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Returns {
            "ks_pvalues": {col: float, ...},
            "effect_sizes": {col: {"cohens_d": float, "interpretation": str}, ...},
            "power_estimates": {col: {"achieved_power": float, "n_for_80pct": int}, ...},
            "reliability_score": float,
            "warnings": List[str],
            "diagnostic_plots": {
                "dist_overlap": "<base64 PNG>",
                "qq_plot": "<base64 PNG>",
            },
            "method_params": dict,
        }
        """
        ks_pvalues: Dict[str, float] = {}
        effect_sizes: Dict[str, Dict[str, Any]] = {}
        power_estimates: Dict[str, Dict[str, Any]] = {}
        stat_warnings: List[str] = []

        # Filter to valid outcome columns present in both DataFrames
        valid_cols = [
            c for c in outcome_cols
            if c in real_control_df.columns and c in vcg_df.columns
        ]

        for col in valid_cols:
            real_vals = pd.to_numeric(real_control_df[col], errors="coerce").dropna().values
            vcg_vals = pd.to_numeric(vcg_df[col], errors="coerce").dropna().values

            if len(real_vals) < 2 or len(vcg_vals) < 2:
                continue

            # KS test
            try:
                with _warnings.catch_warnings():
                    _warnings.simplefilter("ignore")
                    ks_stat, ks_p = stats.ks_2samp(real_vals, vcg_vals)
                ks_pvalues[col] = round(float(ks_p), 6)
                if ks_p < 0.05:
                    stat_warnings.append(
                        f"Distribution of {col} differs significantly between VCG and real controls "
                        f"(KS p={ks_p:.3f})"
                    )
            except Exception:
                ks_pvalues[col] = float("nan")

            # Cohen's d
            try:
                if HAS_PINGOUIN:
                    d = float(pg.compute_effsize(real_vals, vcg_vals, eftype='cohen'))
                else:
                    mean1 = float(np.mean(real_vals))
                    mean2 = float(np.mean(vcg_vals))
                    n1 = len(real_vals)
                    n2 = len(vcg_vals)
                    std1 = float(np.std(real_vals, ddof=1))
                    std2 = float(np.std(vcg_vals, ddof=1))
                    pooled_var = ((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / (n1 + n2 - 2)
                    pooled_std = float(np.sqrt(max(pooled_var, 1e-12)))
                    d = (mean1 - mean2) / pooled_std

                abs_d = abs(d)
                if abs_d < 0.2:
                    interp = "negligible"
                elif abs_d < 0.5:
                    interp = "small"
                elif abs_d < 0.8:
                    interp = "medium"
                else:
                    interp = "large"

                effect_sizes[col] = {
                    "cohens_d": round(float(d), 4),
                    "interpretation": interp,
                }

                if abs_d > 0.5:
                    stat_warnings.append(
                        f"Large effect size for {col}: VCG may not adequately replicate "
                        f"control distribution (|d|={abs_d:.2f})"
                    )
            except Exception:
                effect_sizes[col] = {"cohens_d": float("nan"), "interpretation": "unknown"}

            # Power analysis
            n_real = len(real_vals)
            n_vcg = len(vcg_vals)
            abs_d = abs(effect_sizes.get(col, {}).get("cohens_d", 0.0))
            if np.isnan(abs_d):
                abs_d = 0.0

            achieved_power: float = float("nan")
            n_for_80pct: int = -1

            if HAS_STATSMODELS:
                try:
                    analysis = TTestIndPower()
                    if abs_d > 0:
                        with _warnings.catch_warnings():
                            _warnings.simplefilter("ignore")
                            achieved_power = float(
                                analysis.solve_power(
                                    effect_size=abs_d,
                                    nobs1=n_real,
                                    alpha=0.05,
                                    alternative="two-sided",
                                )
                            )
                        with _warnings.catch_warnings():
                            _warnings.simplefilter("ignore")
                            n80 = analysis.solve_power(
                                effect_size=abs_d,
                                power=0.80,
                                alpha=0.05,
                                alternative="two-sided",
                            )
                        n_for_80pct = int(np.ceil(float(n80))) if n80 is not None else -1
                    else:
                        achieved_power = 0.05  # No effect → power = alpha
                        n_for_80pct = -1
                except Exception:
                    pass
            else:
                # Analytic approximation when statsmodels is unavailable
                # Power ≈ Phi(|d| * sqrt(n/2) - z_alpha/2)
                if abs_d > 0 and n_real > 0:
                    z_alpha = stats.norm.ppf(1 - 0.05 / 2)
                    ncp = abs_d * np.sqrt(n_real / 2.0)
                    achieved_power = float(stats.norm.cdf(ncp - z_alpha))
                    # Solve for n_for_80pct: z_beta = z_alpha - d*sqrt(n/2)
                    # n ≈ 2 * ((z_alpha + z_beta) / d)^2
                    z_beta = stats.norm.ppf(0.80)
                    n_est = 2 * ((z_alpha + z_beta) / max(abs_d, 1e-9)) ** 2
                    n_for_80pct = int(np.ceil(n_est))
                else:
                    achieved_power = 0.05
                    n_for_80pct = -1

            power_estimates[col] = {
                "achieved_power": round(float(achieved_power), 4) if not np.isnan(achieved_power) else None,
                "n_for_80pct": n_for_80pct,
            }

        # Reliability score
        if ks_pvalues:
            valid_ks = [v for v in ks_pvalues.values() if not np.isnan(v)]
            mean_ks = float(np.mean(valid_ks)) if valid_ks else 0.5
        else:
            mean_ks = 0.5

        if effect_sizes:
            valid_d = [abs(v["cohens_d"]) for v in effect_sizes.values() if not np.isnan(v["cohens_d"])]
            mean_smd = float(np.mean(valid_d)) if valid_d else 0.0
        else:
            mean_smd = 0.0

        reliability_score = 0.5 * min(mean_ks / 0.5, 1.0) + 0.5 * max(0.0, 1.0 - mean_smd)
        reliability_score = round(float(np.clip(reliability_score, 0.0, 1.0)), 4)

        if reliability_score < 0.5:
            stat_warnings.append(
                "Low overall reliability score. Consider using more source data."
            )

        # Diagnostic plots
        dist_overlap_b64 = self._plot_distribution_overlap(real_control_df, vcg_df, valid_cols)
        qq_b64 = self._plot_qq(real_control_df, vcg_df, valid_cols)

        # Method params for reproducibility
        method_params = {
            "has_statsmodels": HAS_STATSMODELS,
            "has_pingouin": HAS_PINGOUIN,
            "confidence_level": confidence_level,
            "n_real": len(real_control_df),
            "n_vcg": len(vcg_df),
        }

        return {
            "ks_pvalues": ks_pvalues,
            "effect_sizes": effect_sizes,
            "power_estimates": power_estimates,
            "reliability_score": reliability_score,
            "warnings": stat_warnings,
            "diagnostic_plots": {
                "dist_overlap": dist_overlap_b64,
                "qq_plot": qq_b64,
            },
            "method_params": method_params,
        }

    def _plot_distribution_overlap(
        self,
        real_df: pd.DataFrame,
        vcg_df: pd.DataFrame,
        outcome_cols: List[str],
    ) -> str:
        """
        Creates a faceted figure with KDE overlays.
        real control = blue (#1976d2), VCG = orange (#e65100), alpha=0.6.
        fig size: 4*ncols x 4 inches, max 4 cols per row.
        Returns base64 PNG.
        """
        valid_cols = [
            c for c in outcome_cols
            if c in real_df.columns and c in vcg_df.columns
        ]

        if not valid_cols:
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.text(0.5, 0.5, "No outcome columns to plot",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            return self._fig_to_base64(fig)

        n_cols_plot = min(len(valid_cols), 4)
        n_rows_plot = int(np.ceil(len(valid_cols) / n_cols_plot))
        fig_width = 4 * n_cols_plot
        fig_height = 4 * n_rows_plot

        fig, axes = plt.subplots(n_rows_plot, n_cols_plot,
                                  figsize=(fig_width, fig_height),
                                  squeeze=False)

        for idx, col in enumerate(valid_cols):
            row_idx = idx // n_cols_plot
            col_idx = idx % n_cols_plot
            ax = axes[row_idx][col_idx]

            real_vals = pd.to_numeric(real_df[col], errors="coerce").dropna().values
            vcg_vals = pd.to_numeric(vcg_df[col], errors="coerce").dropna().values

            if len(real_vals) >= 2:
                try:
                    with _warnings.catch_warnings():
                        _warnings.simplefilter("ignore")
                        kde_real = stats.gaussian_kde(real_vals)
                    x_min = min(real_vals.min(), vcg_vals.min() if len(vcg_vals) > 0 else real_vals.min())
                    x_max = max(real_vals.max(), vcg_vals.max() if len(vcg_vals) > 0 else real_vals.max())
                    x_range = np.linspace(x_min - 0.1 * abs(x_min - x_max),
                                          x_max + 0.1 * abs(x_min - x_max), 200)
                    ax.fill_between(x_range, kde_real(x_range), alpha=0.6,
                                    color="#1976d2", label="Real control")
                    ax.plot(x_range, kde_real(x_range), color="#1976d2", lw=1.5)
                except Exception:
                    ax.hist(real_vals, density=True, alpha=0.6, color="#1976d2", label="Real control")

            if len(vcg_vals) >= 2:
                try:
                    with _warnings.catch_warnings():
                        _warnings.simplefilter("ignore")
                        kde_vcg = stats.gaussian_kde(vcg_vals)
                    x_min = min(real_vals.min() if len(real_vals) > 0 else vcg_vals.min(), vcg_vals.min())
                    x_max = max(real_vals.max() if len(real_vals) > 0 else vcg_vals.max(), vcg_vals.max())
                    x_range = np.linspace(x_min - 0.1 * abs(x_min - x_max),
                                          x_max + 0.1 * abs(x_min - x_max), 200)
                    ax.fill_between(x_range, kde_vcg(x_range), alpha=0.6,
                                    color="#e65100", label="VCG")
                    ax.plot(x_range, kde_vcg(x_range), color="#e65100", lw=1.5)
                except Exception:
                    ax.hist(vcg_vals, density=True, alpha=0.6, color="#e65100", label="VCG")

            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel("Value", fontsize=8)
            ax.set_ylabel("Density", fontsize=8)
            ax.legend(fontsize=7)
            ax.tick_params(labelsize=7)

        # Hide unused subplots
        total_subplots = n_rows_plot * n_cols_plot
        for idx in range(len(valid_cols), total_subplots):
            row_idx = idx // n_cols_plot
            col_idx = idx % n_cols_plot
            axes[row_idx][col_idx].set_visible(False)

        fig.suptitle("Distribution Overlap: Real Control vs VCG", fontsize=12, fontweight="bold", y=1.02)
        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_qq(
        self,
        real_df: pd.DataFrame,
        vcg_df: pd.DataFrame,
        outcome_cols: List[str],
    ) -> str:
        """
        QQ plot: real control quantiles (x) vs VCG quantiles (y).
        45-degree reference line in grey.
        Returns base64 PNG.
        """
        valid_cols = [
            c for c in outcome_cols
            if c in real_df.columns and c in vcg_df.columns
        ]

        if not valid_cols:
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.text(0.5, 0.5, "No outcome columns to plot",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            return self._fig_to_base64(fig)

        n_cols_plot = min(len(valid_cols), 4)
        n_rows_plot = int(np.ceil(len(valid_cols) / n_cols_plot))
        fig, axes = plt.subplots(n_rows_plot, n_cols_plot,
                                  figsize=(4 * n_cols_plot, 4 * n_rows_plot),
                                  squeeze=False)

        for idx, col in enumerate(valid_cols):
            row_idx = idx // n_cols_plot
            col_idx = idx % n_cols_plot
            ax = axes[row_idx][col_idx]

            real_vals = np.sort(pd.to_numeric(real_df[col], errors="coerce").dropna().values)
            vcg_vals = np.sort(pd.to_numeric(vcg_df[col], errors="coerce").dropna().values)

            if len(real_vals) < 2 or len(vcg_vals) < 2:
                ax.text(0.5, 0.5, f"{col}\n(insufficient data)",
                        ha="center", va="center", transform=ax.transAxes, fontsize=9)
                ax.set_axis_off()
                continue

            # Interpolate to common quantile grid
            n_quantiles = min(len(real_vals), len(vcg_vals), 100)
            quantile_pts = np.linspace(0, 1, n_quantiles)
            real_q = np.quantile(real_vals, quantile_pts)
            vcg_q = np.quantile(vcg_vals, quantile_pts)

            ax.scatter(real_q, vcg_q, s=20, color="#1976d2", alpha=0.7, zorder=3)

            # 45-degree reference line
            all_vals = np.concatenate([real_q, vcg_q])
            ref_min, ref_max = float(all_vals.min()), float(all_vals.max())
            ref_range = np.linspace(ref_min, ref_max, 100)
            ax.plot(ref_range, ref_range, color="grey", lw=1.5, linestyle="--",
                    alpha=0.8, label="45° reference", zorder=2)

            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel("Real control quantiles", fontsize=8)
            ax.set_ylabel("VCG quantiles", fontsize=8)
            ax.legend(fontsize=7)
            ax.tick_params(labelsize=7)

        # Hide unused subplots
        total_subplots = n_rows_plot * n_cols_plot
        for idx in range(len(valid_cols), total_subplots):
            row_idx = idx // n_cols_plot
            col_idx = idx % n_cols_plot
            axes[row_idx][col_idx].set_visible(False)

        fig.suptitle("Q-Q Plot: Real Control vs VCG", fontsize=12, fontweight="bold", y=1.02)
        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _fig_to_base64(self, fig) -> str:
        """Save figure to BytesIO, base64-encode, close figure, return string."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
