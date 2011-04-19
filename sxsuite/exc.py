# Copyright (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

import socket

S_EINVAL = 1001
S_ELOGINFAILED = 1002
S_ESHUTDOWN = 1003
S_EINVALIDLOGIN = 1004
S_EHEARTBEAT = 1005
S_ELOGINWAIT = 1006
S_EVERSION = 1007
S_ESEQNO = 1008
S_EINMESSAGE = 1009
S_ENOTCONN = 1010
S_ENOUPSTREAM = 1011
S_ENODOWNSTREAM = 1012
S_ENOTUPMODULE = 1013
S_ENOTDOWNMODULE = 1014
S_ETIMEOUT = 1015
S_ENOTINSESSION = 1016
S_ENOTCALLABLE = 1017

_errmsg_table = {
    S_EINVAL: "Invalid value or message",
    S_ELOGINFAILED: "Login failed",
    S_ESHUTDOWN: "Disconnected.",
    S_EINVALIDLOGIN: "Invalid or malformed login message",
    S_EHEARTBEAT: "Too many missing heartbeats",
    S_ELOGINWAIT: "Login time exceeded",
    S_EVERSION: "Incorrect version",
    S_ESEQNO: "Seqeunce number missmatch",
    S_EINMESSAGE: "Invalid message type",
    S_ENOTCONN: "Session not connected",
    S_ENODOWNSTREAM: "No downstream module configured",
    S_ENOUPSTREAM: "No upstream module configured",
    S_ENOTUPMODULE: "Not an upstream module",
    S_ENOTDOWNMODULE: "Not a downstream module",
    S_ETIMEOUT: "Transport timeout occured.",
    S_ENOTINSESSION: "Session not logged in",
    S_ENOTCALLABLE: "Object not callable"
}

def errmsg(errnum):
    try:
        return _errmsg_table[errnum]
    except:
        return 'Unknown error number'

class TransportError(Exception):
    """Transport related errors."""
    def __init__(self, transport, err, msg=''):
        self.source = transport
        if isinstance(err, socket.error):
            self.errno, self.msg = err.args
        else:
            self.errno = err
            self.msg = msg
    
    def __str__(self):
        return "%s: [%d] %s" % (str(self.source), self.errno, self.msg)

class SessionError(Exception):
    """General session errors."""
    def __init__(self, session, errno, msg=''):
        self.source = session
        self.errno = errno
        if msg:
            self.msg = msg
        else:
            self.msg = errmsg(errno)

    def __str__(self):
        return "%s: [%d] %s" % (str(self.source), self.errno, self.msg)


class ConfigError(Exception):
    """Stream configuration errors."""
    def __init__(self, module, errno, msg=''):
        self.source = module
        self.errno = errno
        if msg:
            self.msg = msg
        else:
            self.msg = errmsg(errno)

    def __str__(self):
        return "%s: [%d] %s" % (str(self.source), self.errno, self.msg)
    
