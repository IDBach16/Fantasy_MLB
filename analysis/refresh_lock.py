"""
Cross-process refresh guard. The scheduled refresh_all.py and the dashboard's
"Re-pull" button both drive the SAME real Chrome profile + debug port (9222) —
running them at once makes the launch fail or connect to the wrong instance.
A simple lockfile keeps them from overlapping; a lock older than MAX_AGE_S is
treated as abandoned (crashed run) and taken over.
"""
import os
import time

LOCK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "cache", "refresh.lock")
MAX_AGE_S = 2 * 3600


def held() -> bool:
    return os.path.exists(LOCK) and (time.time() - os.path.getmtime(LOCK)) < MAX_AGE_S


def acquire() -> bool:
    """True if we got the lock; False if a fresh lock is held by another run."""
    if held():
        return False
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def release():
    try:
        os.remove(LOCK)
    except OSError:
        pass
