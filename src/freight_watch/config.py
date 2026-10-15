"""Central configuration. Detection thresholds are documented project assumptions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    history_weeks: int = 8
    own_history_flag_pct: float = 10.0
    peer_flag_pct: float = 20.0
    magnitude_tolerance_pp: float = 2.0
    near_note_days: int = 28

    @property
    def persistent_note_weeks(self) -> int:
        """Window used for persistent step-change notes."""
        return self.history_weeks


DEFAULT_CONFIG = Config()
