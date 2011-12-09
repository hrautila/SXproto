# (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

import asyncore
import errno
import socket
import select
import ssl
import sys
import logging as log

from time import time
import sxsuite.exc as exc
from sxsuite.exc import TransportError

class SSLContext(object):
    def __init__(self,
                 keyfile=None,
                 certfile=None,
                 ca_certs=None,
                 cert_reqs=ssl.CERT_NONE,
                 server_side=False,
                 ssl_version=None):
        self.keyfile = keyfile
        self.certfile = certfile
        self.ca_certs = ca_certs
        self.cert_reqs = cert_reqs
        self.server_side = server_side
        self.ssl_version = ssl_version

    def wrap(self, sock):
        ssl_version = self.ssl_version
        if ssl_version is None:
            if self.server_side:
                ssl_version = ssl.PROTOCOL_SSLv23
            else:
                ssl_version = ssl.PROTOCOL_SSLv3
        nsock = ssl.wrap_socket(sock,
                                keyfile=self.keyfile,
                                certfile=self.certfile,
                                ca_certs=self.ca_certs,
                                cert_reqs=self.cert_reqs,
                                server_side=self.server_side,
                                ssl_version=ssl_version)
        return nsock

    def verify(self, sock):
        return True
                 
class Transport(asyncore.dispatcher):
    """Base class of I/O event based transports based on asyncore.dispatcher.

    """

    IDLE = 0
    CONNECTING = 1
    ACCEPTING = 2
    CONNECTED = 3
    DISCONNECTED = 4
    ERROR = 5

    def __init__(self, reaktor, sock=None, session=None):
        """Create new Transport. Use ``map`` to register for I/O event loop."""
        asyncore.dispatcher.__init__(self, sock, reaktor.map)
        self.session = session
        self.reaktor = reaktor
        self.state = Transport.IDLE

    def __str__(self):
        return str(self.socket)

    def set_session(self, target):
        self.session = target

    def test_session_state(self, state):
        self.session.in_state(state)

    def timeout(self):
        self.session.event_timeout(self, exc.S_ETIMEOUT)

    def start(self):
        self.state = Transport.IDLE
        self.session.event_start(self)

    def stop(self):
        self.session.event_stop(self)

    def handle_read(self):
        """Data available event."""
        self.session.event_readable(self)

    def handle_accept(self):
        """Transport connecting event."""
        self.session.event_accept(self)

    def handle_connect(self):
        """Transport connecting event."""
        self.state = Transport.CONNECTED
        self.session.event_connect(self)

    def handle_close(self):
        """Transport closed event"""
        self.state = Transport.DISCONNECTED
        self.session.event_disconnect(self)

    def handle_write(self):
        """Transport becomes writable event."""
        self.session.event_writable(self)

    def handle_error(self):
        """Transport error. Translates socket errors to ``TransportError``."""
        self.state = Transport.ERROR
        self.session.event_error(self)

    handle_expt = handle_error

    def writable(self):
        """Test if protocol transport writable events are listened."""
        return self.state == Transport.CONNECTING or self.session.writable()

    def readable(self):
        """Test if protocol transport readable events are listened."""
        return  self.state == Transport.CONNECTED or self.session.readable()


    def is_connected(self):
        try:
            addr = self.socket.getpeername()
            return True
        except socket.error, err:
            pass
        return False
    

class InitiatorTransport(Transport):
    """InitiatorTransport for opening TCP connections."""
    
    def __init__(self, reaktor, session=None):
        """Create new TCP initiator transport."""
        Transport.__init__(self, reaktor, None, session)
        self._reconnects = 0
        
    def __str__(self):
        try:
            return "%s: connected to %s" % \
                (self.__class__.__name__, self.getpeername())
        except:
            return "%s: local %s" % \
                (self.__class__.__name__, self.getsockname())

    def ssl_wrap(self, ssl_context):
        nsock = ssl_context.wrap(self.socket)
        self.socket = nsock

    def create(self):
        """Create actual network socket."""
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self.state = Transport.IDLE

    def start(self, target):
        """Connect to target."""
        self.state = Transport.CONNECTING
        self.session.event_start(self)
        self.connect(target)
    
    def handle_connect(self):
        """Connect event."""
        self._reconnects = 0
        Transport.handle_connect(self)


class AcceptorTransport(Transport):
    """Protocol transport for listening incoming connections. """

    def __init__(self, reaktor, session=None):
        """Create new acceptor. """
        Transport.__init__(self, reaktor, None, session)
        self.state = Transport.IDLE

    def __str__(self):
        try:
            return "%s: local %s" % \
                (self.__class__.__name__, self.getsockname())
        except:
            return "%s: unbound" % self.__class__.__name__

    def ssl_wrap(self, ssl_context):
        nsock = ssl_context.wrap(self.socket)
        self.socket = nsock

    def create(self):
        """Create actual network socket."""
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.state = Transport.IDLE

    def start(self, target):
        """Start listening."""
        self.state = Transport.ACCEPTING
        self.session.event_start(self)
        self.bind(target)
        self.listen(5)

    def writable(self):
        return self.state == Transport.ACCEPTING

    def readable(self):
        """Test if protocol transport readable events are listened."""
        return self.state == Transport.ACCEPTING
    
    
class ConnectedTransport(Transport):
    """Protocol transport for live TCP connections."""

    def __init__(self, reaktor, sock, target=None):
        """Create new connected transport bound to ``sock``. """
        Transport.__init__(self, reaktor, None, target)
        self.set_socket(sock)
        if isinstance(sock, socket.socket):
            self.setblocking(0)
        self.state = Transport.CONNECTED
        self.connected = True

    def __str__(self):
        try:
            return "%s: connected to %s" % \
                (self.__class__.__name__, self.getpeername())
        except:
            return "%s: local" % \
                (self.__class__.__name__)
        
    def ssl_wrap(self, ssl_context):
        nsock = ssl_context.wrap(self.socket)
        self.socket = nsock


class PipeTransport(Transport):
    """Protocol transport for live TCP connections."""

    def __init__(self, reaktor, sock, target=None):
        """Create transport connected to multiprocessing.Pipe. """
        Transport.__init__(self, reaktor, None, target)
        self.set_socket(sock)
        self.state = Transport.CONNECTED
        
    def recv(self, size=0):
        data = self.socket.recv()
        return data
    

if sys.platform != 'win32':
     class FileTransport(asyncore.file_dispatcher):
        """Transport for file based channels."""

        def __init__(self, reaktor, fd, session=None):
            """Create new Transport. Use ``map`` to register for I/O event loop."""
            asyncore.file_dispatcher.__init__(self, fd, reaktor.map)
            self.session = session
            self.reaktor = reaktor
            self.state = Transport.CONNECTED

        def __str__(self):
            return str(self.socket)

        def set_session(self, session):
            self.session = session

        def test_session_state(self, state):
            return self.session.in_state(state)

        def handle_read(self):
            """Data available event."""
            self.session.event_readable(self)

        def handle_connect(self):
            """Transport connecting event."""
            self.session.event_connect(self)

        def handle_close(self):
            """Transport closed event"""
            self.state = Transport.DISCONNECTED
            self.session.event_disconnect(self)

        def handle_write(self):
            """Transport becomes writable event."""
            self.session.event_writable(self)

        def handle_error(self):
            """Transport error. Translates socket errors to ``TransportError``."""
            import traceback
            self.state = Transport.ERROR
            self.session.event_error(self)

        handle_expt = handle_error

        def writable(self):
            """Test if protocol transport writable events are listened."""
            return self.session.writable()

        def readable(self):
            """Test if protocol transport readable events are listened."""
            return self.state == Transport.CONNECTED or self.session.readable()

