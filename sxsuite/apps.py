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
    def setup(self, connection, config):
        pass

    def handle(self, data, connection):
        pass

    def finish(self, connection):
        pass

    def __call__(self, data, connection):
        self.handle(data, connection)


class _Subprocess(object):
    
    def __init__(self, target, conn, config):
        self.target = target
        self.conn = conn
        self.init = None
        self.finish = None
        self.running = False
        self.config = config

    def run(self):
        """Run the application data receiving loop.

        This is executed in the subprocess context.
        """
        signal.signal(signal.SIGTERM, self.sigterm)
        logging.debug("starting subprocess in pid: %d [fd %d]",
                      os.getpid(), self.conn.fileno())
        # flush all timers as we are running in separate process
        flush_timers()
        os.closerange(3, self.conn.fileno())

        self.init = getattr(self.target, 'setup', None)
        self.finish = getattr(self.target, 'finish', None)
        if hasattr(self.target, 'handle'):
            self.handler = getattr(self.target, 'handle')
        else:
            self.handler = target
        if not callable(self.handler):
            raise ConfigError(self, exc.E_NOTCALLABLE)

        if callable(self.init):
            self.init(self.conn, self.config)
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
                self.conn.send(e)
        # end while
        if callable(self.finish):
            self.finish(self.conn)
        self.conn.close()

    def run_module(self, modulename):
        import importlib
        self.target = importlib.import_module(modulename)
        self.run()

    def sigterm(self, signum, frame):
        logging.info("SIGTERM caught; terminating ...")
        self.running = False



class ProcessApplication(Application):
    """Run application class in subprocess."""

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
        self.runner = _Subprocess(self.target, self.child, self.config)
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
        """Send data to application."""
        self.parent.send(data)

    def recv(self, data):
        """Handle data received from subprocess application."""
        if isinstance(data, Exception):
            self.log.error("Subprocess exception: %s", str(data))
            raise data
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


class SessionProcess(object):

    def __init__(self, sessionClass, protocol, config):
        self.sessionClass = sessionClass
        self.protocol = protocol
        self.config = config

    def start(self, netname, sslcontext=None):
        self.parent, child = Pipe()
        self.p = Process(target=run_session_process,
                         args=(child, self.sessionClass, self.protocol, self.config, netname))
        self.p.start()
        
    def close(self):
        self.p.terminate()
        self.p.join()


def run_session_process(pipe, sessionClass, protocol, config, netaddr, sslcontext):
    """Run session in separete sub process"""

    from reaktor import Reaktor
    from transport import PipeTransport

    reaktor = Reaktor()
    name = config.get('name', '_unnamed_')
    if 'name' in config:
        del config['name']

    state_path = config.get('state_path', '')
    if 'state_path' in config:
        del config['state_path']
    
    msg_path = config.get('msg_store', '')
    if 'msg_store' in config:
        del config['msg_store']
    
    ses = sessionClass(reaktor, protocol, name=name, store_url=msg_path)

    for key, val in config.items():
        ses.set_conf(key, val)

    pipe_transport = PipeTransport(pipe)
    app = Application(transport=pipe_transport)
    app.linkdown(ses)
    ses.linkup(app)

    if sslcontext is not None:
        ses.ssl_context(sslcontext)

    ses.start(netaddr)
    app.start()
    if state_path:
        ses.state.restore(state_path)
        savelist = [(ses, state_path)]
    reaktor.run(savelist=savelist, exc_handler=exchandler)
    
