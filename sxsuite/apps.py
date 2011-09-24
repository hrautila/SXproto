# Copyright (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

import sys
import signal
import logging
import traceback
import os

from multiprocessing import Process

import sxsuite.exc as exc
from sxsuite.exc import ConfigError, SessionError
from sxsuite.session import *
from sxsuite.timer import flush_timers, run_timers

if sys.platform != 'win32':
    from multiprocessing import Pipe
else:
    # work-around the problem that named pipes cannot be used in select in Windows
    import socket
    import select
    import pickle
    class Connection(object):
        def __init__(self, _sock):
            self._sock = _sock
        
        def recv(self):
            data =  self._sock.recv(40960)
            return pickle.loads(data)

        def send(self, data):
            s = pickle.dumps(data)
            self._sock.send(s)
    
        def fileno(self):
            return self._sock.fileno()
        
        def close(self):
            #self.send(EOFError("closed"))
            self._sock.close()
        
        def poll(self, timeout=None):
            rd, wd, xd = select.select([self.fileno()], [], [], timeout)
            if rd:
                return True
            return False

    def Pipe(duplex=True):
        """Return a pair connected sockets at either end of a pipe."""
        a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        a.bind(('localhost', 0))
        b.bind(('localhost', 0))
        a.connect(b.getsockname())
        b.connect(a.getsockname())
        return Connection(a), Connection(b)


class Application(Session):
    def __init__(self, protocol=None, name='', transport=None):
        Session.__init__(self, protocol, name=name, transport=transport)
        self._state = Session.IDLE

    def in_state(self, state):
        return self._state == state

    def stop(self):
        self._state = Session.STOPPED

    def start(self):
        pass

    def received(self, data):
        """Handle received and validated data.

        Application ``received`` pushes data downstream.
        """
        if self._downlink is not None:
            self._downlink.downstream(data)
        else:
            raise ConfigError(self, exc.S_ENODOWNSTREAM)
        
    def upstream(self, data):
        """Receive data from downstream."""
        self.send(data)

    def downstream(self, data):
        raise ConfigError(self, S_ENOTDOWNMODULE)

class ConsoleApplication(Application):
    """Simple session for reading and writing to console or terminal."""

    def __init__(self, reaktor, name=''):
        Application.__init__(self, LineProtocol(), name=name)
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.transport = FileTransport(reaktor, self.stdin, self)
        self._state = Session.INSESSION
        
    def transmit(self, data):
        self.stdout.write(data)
        self.stdout.flush()

    def event_error(self, transport):
        import traceback
        traceback.print_exc()


class Handler(object):
    def setup(self, connection):
        pass

    def handle(self, data):
        pass

    def finish(self):
        pass

    def __call__(self, data):
        self.handle(data)

class ProcessApplication(Application):

    class Subprocess(object):
        def __init__(self, target, conn):
            self.target = target
            self.conn = conn
            self.init = None
            self.finish = None
            self.running = False
            if hasattr(target, 'setup'):
                self.init = getattr(target, 'setup')
            if hasattr(target, 'finish'):
                self.finish = getattr(target, 'finish')
            if hasattr(target, 'handle'):
                self.handler = getattr(target, 'handle')
            else:
                self.handler = target
            if not callable(self.handler):
                raise ConfigError(self, exc.E_NOTCALLABLE)

        def run(self):
            signal.signal(signal.SIGTERM, self.sigterm)
            logging.debug("starting subprocess in pid: %d [fd %d]",
                          os.getpid(), self.conn.fileno())
            # flush all timers as we are running in separate process
            flush_timers()
            os.closerange(3, self.conn.fileno())
            if callable(self.init):
                self.init(self.conn)
            self.running = True
            while self.running:
                try:
                    readable = self.conn.poll(0.5)
                    run_timers()
                    if not readable:
                        continue
                    data = self.conn.recv()
                except (IOError, KeyboardInterrupt), ex:
                    break
                except Exception, e:
                    logging.error("Subprocess recv failed: %s", str(e))
                    break
                try:
                    result = self.handler(data, self.conn)
                    if result is not None:
                        self.conn.send(result)
                except Exception, e:
                    logging.error("Subprocess %s raised %s", str(self.target), str(e))
            # end while
            if callable(self.finish):
                self.finish(self.conn)
            self.conn.close()

        def sigterm(self, signum, frame):
            logging.info("SIGTERM caught; terminating ...")
            self.running = False

    def __init__(self, reaktor, target, name=''):
        Application.__init__(self, None, name)
        self.target = target
        self._reaktor = reaktor
        self._process = None
        self.parent = None
        self.child = None
        self.transport = None
        self.runner = None

    def start(self):
        signal.signal(signal.SIGCHLD, self._sigchld)
        self.parent, self.child = Pipe(duplex=True)
        logging.debug("parent conn %d, child %d",
                      self.parent.fileno(), self.child.fileno())
        self.transport = ConnectedTransport(self._reaktor, self.parent, self)
        self.runner = ProcessApplication.Subprocess(self.target, self.child)
        self._process = Process(target=self.runner.run)
        self._process.start()

    def _close(self, timeout):
        self._process.join(timeout)
        if self.transport is not None:
            # this closes also parent channel
            self.transport.close()
            self.transport.del_channel()
        self.child = self.parent = self.transport = None

    def _sigchld(self, signum, frame):
        self._close(0.5)

    def stop(self):
        self._process.terminate()
        self._close(2.0)

    def send(self, data):
        self.parent.send(data)

    def recv(self, data):
        self.received(data)

    def event_readable(self, transport):
        assert(transport == self.transport)
        data = self.transport.socket.recv()
        self.log.debug("received from app: %s", str(data))
        if data is not None:
            self.recv(data)

    def event_error(self, transport):
        typ, ex, tb = sys.exc_info()
        if typ != KeyboardInterrupt:
            self.log.debug("process: %s", str(ex))

