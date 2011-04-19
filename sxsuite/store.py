# (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

import os
import pickle
from urlparse import urlparse

def open_store(url):
    r = urlparse(url)
    if r.scheme == 'file':
        return MessageFileStore(r.path)
    return None

class MessageFileStore(object):
    def __init__(self, path):
        self.path = path
        self.fd = None
        
    def open(self):
        if self.fd is None:
            self.fd = open(self.path, 'a+')

    def save(self, num, msg):
        self.open()
        self.fd.seek(0, os.SEEK_END)
        pickle.dump([num, msg], self.fd)
        self.fd.flush()

    def tell(self):
        if self.fd is None:
            return 0
        return self.fd.tell()

    def find(self, num, pos=0):
        self.open()
        if pos != None:
            self.fd.seek(pos, os.SEEK_SET)

        while True:
            try:
                rec = pickle.load(self.fd)
                if rec[0] == num:
                    break
                elif rec[0] > num:
                    return -1, None
            except EOFError, e:
                return -1, None
        return rec[0], rec[1]
        
    def next(self, num):
        self.open()
        try:
            rec = pickle.load(self.fd)
        except EOFError, e:
            return -1, None
        return rec[0], rec[1]

            
