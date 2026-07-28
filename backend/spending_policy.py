"""Per-run programmable USDC spending controls for the Obol agent.

The policy is deliberately request-scoped: two agents can use the same Obol
deployment with different risk tolerances without changing process-wide
environment variables. Environment variables remain supported as defaults so
existing callers keep the behaviour they had before policies were introduced.
"""
from dataclasses import dataclass
import math
import os


class PolicyValidationError(ValueError):
    """Raised when a caller supplies an unsafe or malformed spending policy."""


def _env_optional_float(name):
    raw = (os.getenv(name) or "").strip()
    return float(raw) if raw else None


def _env_optional_int(name):
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else None


def _number(value, field):
    if isinstance(value, bool):
        raise PolicyValidationError(f"{field} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise PolicyValidationError(f"{field} must be a number")
    if not math.isfinite(parsed):
        raise PolicyValidationError(f"{field} must be finite")
    return parsed


def _optional_number(value, field, default):
    return default if value is None else _number(value, field)


@dataclass(frozen=True)
class SpendingPolicy:
    """A deterministic guardrail set applied before every USDC transfer."""

    total_budget_usdc: float
    reserve_usdc: float
    max_price_usdc: float | None
    min_relevance: float
    max_purchases: int | None
    coverage_target: float

    @property
    def spendable_budget_usdc(self):
        return max(0.0, self.total_budget_usdc - self.reserve_usdc)

    @classmethod
    def from_input(cls, total_budget_usdc, raw=None):
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise PolicyValidationError("policy must be an object")
        allowed_fields = {
            "reserve_usdc",
            "max_price_usdc",
            "min_relevance",
            "max_purchases",
            "coverage_target",
        }
        unknown_fields = sorted(set(raw) - allowed_fields)
        if unknown_fields:
            raise PolicyValidationError(
                f"unknown policy field(s): {', '.join(unknown_fields)}"
            )

        total = _number(total_budget_usdc, "budget_usdc")
        if total <= 0:
            raise PolicyValidationError("budget_usdc must be > 0")

        reserve_default = _env_optional_float("OBOL_RESERVE_USDC") or 0.0
        max_price_default = _env_optional_float("OBOL_MAX_PRICE_USDC")
        min_relevance_default = float(os.getenv("OBOL_MIN_RELEVANCE", "0.35"))
        max_purchases_default = _env_optional_int("OBOL_MAX_PURCHASES")
        coverage_default = float(os.getenv("OBOL_COVERAGE_TARGET", "0.8"))

        reserve = _optional_number(raw.get("reserve_usdc"), "policy.reserve_usdc",
                                   reserve_default)
        max_price = _optional_number(raw.get("max_price_usdc"),
                                     "policy.max_price_usdc", max_price_default)
        min_relevance = _optional_number(raw.get("min_relevance"),
                                         "policy.min_relevance",
                                         min_relevance_default)
        coverage_target = _optional_number(raw.get("coverage_target"),
                                           "policy.coverage_target",
                                           coverage_default)

        raw_max_purchases = raw.get("max_purchases", max_purchases_default)
        if raw_max_purchases is None:
            max_purchases = None
        else:
            parsed_max = _number(raw_max_purchases, "policy.max_purchases")
            if not parsed_max.is_integer():
                raise PolicyValidationError("policy.max_purchases must be an integer")
            max_purchases = int(parsed_max)

        if reserve < 0:
            raise PolicyValidationError("policy.reserve_usdc must be >= 0")
        if reserve > total:
            raise PolicyValidationError(
                "policy.reserve_usdc cannot exceed budget_usdc"
            )
        if max_price is not None and max_price < 0:
            raise PolicyValidationError("policy.max_price_usdc must be >= 0")
        if not 0 <= min_relevance <= 1:
            raise PolicyValidationError("policy.min_relevance must be between 0 and 1")
        if max_purchases is not None and max_purchases < 0:
            raise PolicyValidationError("policy.max_purchases must be >= 0")
        if not 0 < coverage_target <= 1:
            raise PolicyValidationError(
                "policy.coverage_target must be greater than 0 and at most 1"
            )

        return cls(
            total_budget_usdc=round(total, 6),
            reserve_usdc=round(reserve, 6),
            max_price_usdc=(round(max_price, 6) if max_price is not None else None),
            min_relevance=round(min_relevance, 4),
            max_purchases=max_purchases,
            coverage_target=round(coverage_target, 4),
        )

    def to_dict(self):
        return {
            "total_budget_usdc": self.total_budget_usdc,
            "spendable_budget_usdc": round(self.spendable_budget_usdc, 6),
            "reserve_usdc": self.reserve_usdc,
            "max_price_usdc": self.max_price_usdc,
            "min_relevance": self.min_relevance,
            "max_purchases": self.max_purchases,
            "coverage_target": self.coverage_target,
        }

    def describe(self):
        price_cap = (
            f"${self.max_price_usdc:.3f} per source"
            if self.max_price_usdc is not None else "no extra per-source cap"
        )
        purchase_cap = (
            str(self.max_purchases)
            if self.max_purchases is not None else "unlimited"
        )
        return (
            f"Spendable ${self.spendable_budget_usdc:.3f} of "
            f"${self.total_budget_usdc:.3f}; reserve ${self.reserve_usdc:.3f}; "
            f"{price_cap}; relevance >= {self.min_relevance:.2f}; "
            f"max paid reads {purchase_cap}; stop at "
            f"{self.coverage_target:.0%} coverage."
        )
