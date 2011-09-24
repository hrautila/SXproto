# (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

import socket
import errno
import sys
import logging
import traceback
import ssl

from time import time

import sxsuite.exc as exc
from sxsuite.transport import *
from sxsuite.protocol import LineProtocol
from sxsuite.exc import TransportError, SessionError, ConfigError
from sxsuite.timer import add_timer, del_timer

_session_counter = 0

class SessionBase(object):
    def __init__(self, protocol):
        self.protocol = protocol
        if protocol is not None:
            self.protocol.session = self
        self._downlink = None
        self._uplink = None

    def linkup(self, app):
        """Set uplink application to receive messages."""
        self._uplink = app

    def linkdown(self, app):
        """Set downlink application to send messages to."""
        self._downlink = app

    def recv(self, data):
        """Receive wire format data."""
        if protocol is None:
            self.received(data)
        else:
            self.protocol.received(data)

    def send(self, data):
        """Send data downstream."""
        if self.protocol is None:
            self.transmit(data)
        else:
            self.protocol.transmit(data)

    def received(self, data):
        """Handle received and validated data."""
        if self._uplink is not None:
            try:
                logging.debug("push upstream: %s", type(self._uplink))
                self._uplink.upstream(data)
            except Exception, e:
                logging.debug("session.received: %s", str(e))
                traceback.print_exc()
                raise e
        else:
            raise ConfigError, (self, exc.S_ENOUPSTREAM)
        
    def transmit(self, data):
        if self._downlink is not None:
            self._downlink.downstream(data)
        else:
            raise ConfigError, (self, exc.S_ENODOWNSTREAM)

    def upstream(self, data):
        """Push data upstream."""
        self.recv(data)

    def downstream(self, data):
        """Push data downstream."""
        self.send(data)


class Session(SessionBase):

    """Implements basic session state machine.

    Session is bottom module and trying to push data upstream will
    raise exception.

    """
    IDLE = 0
    LOGIN = 1
    SSL_INIT = 2
    INSESSION = 3
    LOGOUT = 4
    INERROR = 5
    STOPPED = 6

    _state_names = {
        IDLE: "IDLE",
        LOGIN: "LOGIN",
        SSL_INIT: "SSL_INIT",
        INSESSION: "INSESSION",
        LOGOUT: "LOGOUT",
        INERROR: "INERROR",
        STOPPED: "STOPPED",
        }

    def __init__(self, protocol, name='', transport=None, server=False):
        SessionBase.__init__(self, protocol)
        self.transport = transport
        self.server = server
        self.config = {}
        self.last_send = 0
        self.last_receive = 0
        self.hb_interval = 0
        self.watchdog_secs = 0
        self._state = Session.IDLE
        self._inb = ''
        self._outq = []
        self._direct = False
        self._tid = None
        if name:
            self.name = name
        else:
            global _session_counter
            self.name = "session-%d" % _session_counter
            _session_counter += 1
        if transport is not None:
            transport.set_session(self)

    log = logging

    def __str__(self):
        return "%s [%s] %s" % (self.name,
                               str(self.protocol),
                               Session._state_names[self._state])

    def in_state(self, state):
        """Test if ``session`` in ``state``."""
        return self._state == state

    # UP/DOWN methods

    def set_conf(self, key, value):
        self.config[key] = value

    def get_conf(self, key, default=''):
        return self.config.get(key, default)

    def save(self, *args):
        """Save session state."""
        pass

    def restore(self, *args):
        """Restore session state."""
        pass

    def upstream(self, data):
        raise ConfigError, (self, exc.S_ENOTUPMODULE)

    def downstream(self, data):
        self.send(data)

    def recv(self, data):
        """Receive message from downstream."""
        self.last_receive = time()
        self._inb += data
        lines, self._inb = self.protocol.parser(self._inb)

        if not lines:
            return

        if self._state == Session.LOGIN:
            login_m = self.protocol.validate(lines.pop(0))
            if login_m is None:
                raise SessionError, (self, exc.S_ELOGIN)
            self.log.debug("VALIDATE LOGIN: '%s'", str(login_m))
            if self.protocol.login_auth(login_m, self.server):
                self._state = Session.INSESSION
                del_timer(self._tid)
            self._start_hb_watchdog()

        if self._state == Session.INSESSION:
            for line in lines:
                msg = self.protocol.validate(line)
                if msg is None:
                    raise SessionError, (self, exc.S_EINVAL)
                self.protocol.received(msg, self.server)


    def send(self, data):
        # if self._state != Session.INSESSION:
        #    raise SessionError(exc.S_ENOTINSESSION)
        if self.protocol is None:
            self.transmit(data)
        else:
            self.protocol.transmit(data)

    def transmit(self, data):
        """Send data downstream.

        If this is the bottom layer write it to transport. Data
        is assume to be in ``wire-format``.
        """
        if self._direct:
            if self.transport is None:
                raise TransportError, (self, exc.S_ENOTCONN)
            self.transport.send(data)
            self.last_send = time()
        else:
            self._outq.append(data)
        #self.log.debug("Out queue length: %d", len(self._outq))

    def writable(self):
        return len(self._outq) > 0 or self._state == Session.SSL_INIT

    def readable(self):
        return self._state != Session.IDLE

    def start(self, *args):
        pass

    def stop(self, *args):
        pass

    # TRANSPORT events

    def event_start(self, transport):
        # self.log.debug("START [DEF]")
        pass

    def event_connect(self, transport):
        pass

    def event_disconnect(self, transport):
        pass

    def event_writable(self, transport):
        """Write data to transport."""
        connected = transport.state == Transport.CONNECTED
        if self.transport is None:
            raise TransportError, (self, exc.S_ENOTCONN)
        assert(transport == self.transport)
        if connected and len(self._outq) > 0:
            data = self._outq.pop(0)
            self.transport.send(data)
            self.last_send = time()

    def event_readable(self, transport):
        assert(transport == self.transport)
        data = transport.recv(10420)
        if not data:
            return 
        self.recv(data)

    def event_timeout(self, transport, reason):
        self.log.debug("TIMEOUT")
        transport.close()
        transport.del_channel()
        self._state = Session.IDLE
        raise SessionError, (self, reason)

    def event_stop(self, transport):
        transport.close()
        transport.del_channel()
        self._state = Session.IDLE

    def event_error(self, transport):
        typ, ex, tb = sys.exc_info()
        import traceback
        self.log.debug("ERROR %s: %s", typ, str(ex))
        error_no = 0
        traceback.print_exc()
        raise ex
        
    # Private methods

    def _start_hb_watchdog(self):
        del_timer(self._tid)
        self.watchdog_secs = self.get_conf('watchdog_interval', 0)
        self.hb_interval = self.get_conf('heartbeat_interval', 0)
        if self.watchdog_secs <= 0 and self.hb_interval > 0:
            self.watchdog_secs = max(1, self.hb_interval/2)
        if self.watchdog_secs > 0:
            # self.log.debug("arming hb status checker %d sec", self.watchdog_secs)
            self._tid = add_timer(self.watchdog_secs, self._check_hb_status)

    def _check_hb_status(self):
        now = time()
        if now - self.last_send >= self.hb_interval:
            # self.log.debug("last send %d secs ago", now-self.last_send)
            self.protocol.send_hb()
            self.last_send = now

        if now - self.last_receive >= 3 * self.hb_interval:
            self.log.debug("last receive %d secs ago", now-self.last_receive)
            self.event_timeout(self.transport, exc.S_EHEARTBEAT)
            return

        self._tid = add_timer(self.watchdog_secs, self._check_hb_status)

    def _login_timeout(self):
        self.log.warning("Login time exceeded")
        self.event_timeout(self.transport, exc.S_ELOGINWAIT)


class TCPSession(Session):

    def __init__(self, reaktor, protocol, name='', server=False, transport=None):
        Session.__init__(self, protocol, name=name, server=server, transport=transport)
        self.listener = None
        self.transport = transport
        self._last_address = None
        self._ssl = None
        if transport is None:
            if self.server:
                self.listener = AcceptorTransport(reaktor, self)
                self.listener.create()
            else:
                self.transport = InitiatorTransport(reaktor, self)
                self.transport.create()

    def ssl_context(self, context):
        self._ssl = context

    def start(self, *args):
        address = args[0]
        self.hb_interval = self.get_conf('heartbeat_interval', 0)
        if self.server:
            self.log.debug("LISTEN ON %s", address)
            #if self._ssl:
            #    self.listener.ssl_wrap(self._ssl)
            self.listener.start(address)
        else:
            self._last_address = address
            self.log.debug("CONNECT TO: %s", address)
            self.transport.start(address)
        
    def stop(self):
        self.log.debug("Stopping: %s", str(self))
        if self.listener is not None:
            #self.log.warning("Closing listen transport: %s", str(self))
            self.listener.close()
            self.listener.del_channel()

        if self.transport is not None:
            #self.log.warning("Closing forcibly open session: %s", str(self))
            self.transport.close()
            self.transport.del_channel()

        del_timer(self._tid)
        self._state = Session.STOPPED

    def event_start(self, transport):
        if self.server:
            return

        self.log.debug("CREATE CONNECT TIMER")
        timeout_sec = self.get_conf('connect_timeout', default=30)
        self._tid = add_timer(int(timeout_sec), transport.timeout)

    def event_stop(self, transport):
        self.stop()

    def event_accept(self, transport):
        self.log.debug("ACCEPT [%d]", self._state)
        if not self.server:
            self.log.debug("ACCEPT event for client side")
            return

        assert(transport == self.listener)
        sock, client_address = self.listener.accept()
        if self.transport is not None:
            self.log.info("ALREADY connected")
            sock.close()
            
        self.log.debug("ACCEPTED: %s [%s]", str(sock.getpeername()), type(sock))
        if self.transport is None:
            self.transport = ConnectedTransport(transport.reaktor, sock, self)
            self.transport.add_channel()
            if self._state == Session.IDLE and self._ssl is not None:
                self.transport.socket.setblocking(1)
                self._state = Session.SSL_INIT
                self.transport.ssl_wrap(self._ssl)
                return
            self.listener.listen(0)

        self._state = Session.LOGIN
        timeout_sec = self.get_conf('login_wait_time', 20)
        self._tid = add_timer(timeout_sec, self._login_timeout)


    def event_writable(self, transport):
        if self._state == Session.SSL_INIT:
            self.log.debug("End of TLS/SSL handshake ")
            if not self._ssl.verify(self.transport.socket):
                self.log.debug("TLS/SSL verify failed")
                self._disconnect()
                return 

            # TLS/SSL peer accepted
            self._state = Session.LOGIN
            self.transport.socket.setblocking(0)
            if not self.server:
                self.protocol.send_login()
            self._arm_login_timer()
            return

        Session.event_writable(self, transport)

    def event_connect(self, transport):
        if self.server:
            self.log.debug("CONNECT event for server side")
            return

        self.log.debug("CONNECTED TO %s", str(transport.getpeername()))
        if self._state == Session.IDLE and self._ssl is not None:
            self.log.debug("Start TLS/SSL handshake ")
            self._state = Session.SSL_INIT
            self.transport.socket.setblocking(1)
            self.transport.ssl_wrap(self._ssl)
            self.log.debug("sock %s", str(transport.socket))
            return

        self._state = Session.LOGIN
        self.protocol.send_login()
        self._arm_login_timer()
        
    def event_disconnect(self, transport):
        self.log.debug("DISCONNECT")
        assert(transport == self.transport)
        self._disconnect()

    def event_error(self, transport):
        """Handle errors on transport."""
        # assert(transport == self.transport)
        #self.log.debug("t: %s, s.t: %s", str(transport), str(self.transport))
        typ, ex, tb = sys.exc_info()
        self.log.debug("ERROR %s: %s", typ, str(ex))
        error_no = 0
        if typ == socket.error:
            error_no, errstr = ex.args
            if self.transport is not None:
                self.transport.close()
                self.transport.del_channel()
            if error_no in [errno.ECONNREFUSED,
                            errno.ESHUTDOWN,
                            errno.ETIMEDOUT,
                            errno.ECONNRESET]:
                self._state = Session.IDLE
                if self.server:
                    self._disconnect_client()
                else:
                    self._arm_reconnect()
                return
            else:
                raise TransportError, (self, error_no, errstr)

        elif typ == ssl.SSLError:
            if ex.errno in [ssl.SSL_ERROR_WANT_READ,
                            ssl.SSL_ERROR_WANT_WRITE]:
                return

            self.log.debug("SSLError: %s", str(ex))
            if self.transport is not None:
                self.transport.close()
                self.transport.del_channel()
            if ex.errno in [ssl.SSL_ERROR_EOF]:
                self._state = Session.IDLE
                if self.server:
                    self._disconnect_client()
                else:
                    self._arm_reconnect()
            else:
                raise ex

        else:
            self.log.debug("event_error: %s\n %s",
                           ex.__class__.__name__, traceback.format_exc())
            raise ex

    def event_timeout(self, transport, reason):
        self.log.debug("TIMEOUT")
        # assert(transport == self.transport)
        self._disconnect()

    def _arm_login_timer(self):
        del_timer(self._tid)
        timeout_sec = int(self.get_conf('login_wait_time', 20))
        self.log.debug("arming login timer %d", timeout_sec)
        self._tid = add_timer(timeout_sec, self._login_timeout)

    def _arm_reconnect(self):
        if self.server:
            return
        del_timer(self._tid)
        timeout_sec = self.get_conf('reconnect_interval', 5)
        self._tid = add_timer(timeout_sec, self._request_reconnect)
        
    def _request_reconnect(self):
        del_timer(self._tid)
        self.log.debug("RECONNECT: %s", self._last_address)
        self.transport.create()
        if self._ssl is not None:
            self.transport.ssl_wrap(self._ssl)
        self.transport.add_channel()
        self.transport.start(self._last_address)

    def _disconnect(self):
        self.transport.close()
        self.transport.del_channel()
        self._state = Session.IDLE
        del_timer(self._tid)
        if self.server:
            self._disconnect_client()
        else:
            self._arm_reconnect()
        
    def _disconnect_client(self):
        self._state = Session.IDLE
        del_timer(self._tid)
        if self.listener is not None:
            # delete old client transport
            del self.transport
            self.transport = None
            self.listener.listen(5)


class Client(TCPSession):
    """Implements client side of session.

    Send protocol LOGIN as first message to server side. Excepts first
    message coming from server to be LOGIN response.
    After successfull login subsequent messages are handled by protocol receiver.
    """
    def __init__(self, reaktor, protocol, name=''):
        TCPSession.__init__(self, reaktor, protocol, name, server=False)



class Server(TCPSession):
    """Implements server side of session.

    Excepts first message coming from client to be login message.
    After that subsequent messages are handled by protocol receiver.
    """
    def __init__(self, reaktor, protocol, name='', transport=None):
        TCPSession.__init__(self, reaktor, protocol,
                            name, server=True, transport=transport)



class ConsoleSession(Session):
    def __init__(self, reaktor, protocol, name=''):
        Session.__init__(self, protocol, name=name)
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.transport = FileTransport(reaktor, self.stdin, self)
        self._state = Session.INSESSION

