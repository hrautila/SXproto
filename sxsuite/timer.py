# (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

"""
Simple syncronous timers. 

To fire them some event loop must periodically call for ``run_timers``.
Positive side of this simple implementation is that there are no race conditions
with event loop functions.
"""
import logging
import sys
import os

_timer_list = []
_timer_counter = 0

from time import time

def add_timer(timeout, func):
    """Add ``func`` to execute in ``timeout`` seconds. ``Timeout`` can
    be float. Returns interger ``timer id``.
    """
    global _timer_list, _timer_counter

    fire_at = time() + timeout

    _timer_counter += 1
    timer_id = _timer_counter

    for n in xrange(len(_timer_list)):
        t, tid, f = _timer_list[n]
        if fire_at > t:
            next

        if fire_at <= t:
            _timer_list.insert(n, [fire_at, timer_id, func])
            fire_at = 0
        break

    if fire_at != 0:
        _timer_list.append([fire_at, timer_id, func])

    return timer_id

def del_timer(timer_id):
    """Remove timer with id ``timer_id``."""
    global _timer_list
    if not _timer_list:
        return
    if _timer_list[0][1] == timer_id:
        _timer_list.pop(0)
    else:
        _timer_list = filter(lambda x: x[1] != timer_id, _timer_list)


def flush_timers():
    global _timer_list
    _timer_list = []

def list_timers():
    global _timer_list
    return _timer_list

def run_timers():
    _run_until(time())

def _run_until(t):
    """Fire timers until time ``t``."""
    global _timer_list
    if not _timer_list:
        return

    if _timer_list[0][0] > t:
        return

    while _timer_list and _timer_list[0][0] <= t:
        r, td, func = _timer_list.pop(0)
        func()
        t = time()

        
if sys.platform != 'win32':
    """
    These ``itimer`` functions provide UNIX signal based timer implementation.
    """
    import signal

    def _arm_itimer():
        global _timer_list
        if _timer_list:
            t = _timer_list[0][0] - time()
            if t > 0:
                signal.signal(signal.SIGALRM, _run_timer)
                signal.setitimer(signal.ITIMER_REAL, t, 0)
            else:
                _run_timer()

    def _run_timer(signo, frame):
        """Run timer firing now. """
        _run_until(time())
        _arm_itimer()

    def add_itimer(timeout, func):
        signal.setitimer(signal.ITIMER_REAL, 0)
        tid = add_timer(timeout, func)
        _arm_itimer()
        return tid

    def del_itimer(timer):
        signal.setitimer(signal.ITIMER_REAL, 0)
        tid = del_timer(timer)
        _arm_itimer()
        return tid

    def block_itimers():
        """Block timers."""
        signal.setitimer(signal.ITIMER_REAL, 0)

    def unblock_itimers():
        """Unblock timers. Fires all that are past."""
        _run_until(time())
        _arm_itimer()


else:
    pass

