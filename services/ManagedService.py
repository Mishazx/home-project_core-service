from typing import List, Dict, Optional
import subprocess
from dataclasses import dataclass, field

@dataclass
class ManagedService:
    name: str
    command: List[str]
    cwd: Optional[str]
    healthcheck_url: Optional[str]
    process: Optional[subprocess.Popen] = field(default=None, init=False)
    depends_on: List[str] = field(default_factory=list)
    # Политика рестартов
    restart_backoff_sec: int = 2
    backoff_max_sec: int = 30
    backoff_multiplier: float = 2.0
    restart_window_sec: int = 60
    restart_limit_in_window: int = 5
    _restart_timestamps: List[float] = field(default_factory=list, init=False)
    last_start_ts: float = field(default=0.0, init=False)