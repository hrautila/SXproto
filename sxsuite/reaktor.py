# (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

import logging
import asyncore
import traceback

from sxsuite.exc import SessionError, TransportError
from sxsuite.session import Session
from sxsuite.timer import run_timers, add_timer

class Reaktor(object):
    def __init__(self):
        self.map = {}
        self._savelist = []
        self._stid = None

    def run(self, savelist=[]):
        self._savelist = savelist
        if self._savelist:
            self._stid = add_timer(5, self.save_states)

        while self.map and not self.stopped():
            try:
                asyncore.loop(0.5, False, self.map, 1)
                run_timers()
            except KeyboardInterrupt, ke:
                for t in self.map.values():
                    t.session.stop()
                # break
            except SessionError, se:
                logging.debug( "reaktor session error: %s", str(se))
                logging.debug( "transport: %s", str(se.source.transport))
            except Exception, e:
                logging.debug("reaktor loop: %s", str(e))
                traceback.print_exc()
                break

        logging.info("all sessions stopped")

    def save_states(self):
        for obj, path in self._savelist:
            try:
                obj.save(path)
            except:
                logging.debug( "reaktor: saving failed for %s", str(obj))
        self._stid = add_timer(5, self.save_states)

    def status(self):
        t = self.map.values()
        return map(lambda x: (x.test_session_state(Session.STOPPED), x.session), t)

    def stopped(self):
        transports = self.map.values()
        return all(map(lambda x: x.test_session_state(Session.STOPPED), transports))

    def stop(self):
        for t in self.map.values():
            t.stop()
        
    def add_channel(self, fd, obj):
        self.map[fd] = obj

    def del_channel(self, fd):
        try:
            del self.map[fd]
        except:
            pass

    def sigterm(self, signo, frame):
        logging.debug("SIGTERM [%d] received", signo)
        for t in self.map.values():
            t.stop()
        logging.debug("reaktor map after stop: %s", str(self.map))
