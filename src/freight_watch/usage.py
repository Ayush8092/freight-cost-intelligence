"""Track provider-reported token usage and estimated model cost."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UsageTracker:
    model: str = "none (deterministic templates)"
    input_price_per_million_usd: float = 0.0
    output_price_per_million_usd: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Add one call's PROVIDER-REPORTED token usage."""
        self.calls += 1
        self.input_tokens += int(input_tokens)
        self.output_tokens += int(output_tokens)

    @property
    def estimated_cost_usd(self) -> float:
        return (self.input_tokens * self.input_price_per_million_usd
                + self.output_tokens * self.output_price_per_million_usd) / 1_000_000

    def to_dict(self, shipments_rows: int, route_weeks: int, candidates: int) -> dict:
        return {
            "model": self.model,
            "llm_calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "token_source": "provider usage metadata (none: no provider was called)" if self.calls == 0
                            else "provider usage metadata",
            "run_scope": {"shipment_rows": shipments_rows, "route_weeks_computed": route_weeks,
                          "candidate_route_weeks_explained": candidates},
            "note": ("The core pipeline uses local TF-IDF retrieval and rule-based validation; reasons are "
                     "templated from validated facts. No model generated any text, so no tokens were "
                     "produced or billed. Local CPU time and one-time package installs are not counted."),
        }
