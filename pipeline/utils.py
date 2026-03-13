import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

DATA_DIR = Path(__file__).parent.parent / "source_data"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

def get_anthropic_client():
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key or key == "your_key_here":
        raise ValueError("ANTHROPIC_API_KEY not set in .env file")
    return anthropic.Anthropic(api_key=key)


import time as _time

class Progress:
    """
    Simple inline progress meter. Renders a bar that updates in place.

    Usage:
        p = Progress(total=485, label="Extracting cities")
        for i, item in enumerate(items):
            p.update(i + 1, suffix="Los Angeles")
        p.done()
    """

    BAR_WIDTH = 30

    def __init__(self, total, label="Progress"):
        self.total = total
        self.label = label
        self.start_time = _time.time()
        self._last_print = 0
        self.update(0)

    def update(self, current, suffix=""):
        now = _time.time()
        # Throttle to max 4 redraws/sec to avoid flicker
        if current != self.total and now - self._last_print < 0.25:
            return
        self._last_print = now

        pct = current / self.total if self.total else 0
        filled = int(self.BAR_WIDTH * pct)
        bar = "#" * filled + "-" * (self.BAR_WIDTH - filled)

        elapsed = now - self.start_time
        if current > 0 and pct < 1:
            eta_sec = (elapsed / current) * (self.total - current)
            eta = _fmt_time(eta_sec)
        elif pct >= 1:
            eta = f"done in {_fmt_time(elapsed)}"
        else:
            eta = "--:--"

        suffix_str = f"  {suffix}" if suffix else ""
        line = f"\r{self.label}: [{bar}] {current}/{self.total} ({pct*100:.0f}%)  ETA {eta}{suffix_str}"
        # Pad to clear previous longer lines
        print(line.ljust(100), end="", flush=True)

    def done(self, message=None):
        self.update(self.total)
        print()  # newline after bar
        if message:
            print(message)


def _fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m{s:02d}s"
