# (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

"""
Session protocol interfaces.
"""

import sxsuite.exc as exc
from sxsuite.exc import SessionError

class SessionProtocol(object):
    def __init__(self, version=None):
        self.session = None
        
    def __str__(self):
        return self.__class__.__name__

    def received(self, data, server=False):
        """Handle data coming from transport."""
        self.session.received(data)

    def transmit(self, data):
        """Send to session."""
        self.session.transmit(data)

    def login_auth(self, data, server=False):
        """Verify login. Default client client login authentication."""
        return True

    def send_login(self):
        """Send login data to transport."""
        pass

    def send_hb(self):
        """Send heartbeat to transport."""
        pass

    def parser(self, data):
        return [data], ''

    def validate(self, data):
        return data


class LineProtocol(SessionProtocol):
    """Simple line protocol with message terminated with new-lines."""
    def __init__(self, version=None):
        SessionProtocol.__init__(self)
        
    def received(self, data, server=False):
        """Handle data coming from transport."""
        self.session.received(data)

    def transmit(self, data):
        """Handle data going to transport."""
        self.session.transmit(data + '\n')

    def login_auth(self, data, server=False):
        """Verify login."""
        if not server:
            if data != 'OK':
                raise SessionError, (self.session, exc.S_ELOGINFAILED)
            return True
        if server:
            if data != 'LOGIN':
                raise SessionError, (self.session, exc.S_EINVALIDLOGIN)
            self.transmit('OK')
        return True

    def send_login(self):
        """Send login data to transport."""
        self.transmit("LOGIN")

    def send_hb(self):
        """Send heartbeat to transport."""
        self.transmit("I am alive")

    def parser(self, data):
        """Split incoming data to complete messages."""
        lines = data.replace('\r', '').split('\n')
        rem = lines.pop(-1)
        return lines, rem
    
    def validate(self, data):
        if len(data) > 0 and data[0].isupper():
            return data
        return None
