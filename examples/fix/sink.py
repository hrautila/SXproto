
import sys
import logging
import traceback

import sxsuite.exc as exc
from sxsuite.fix import FixClient, FixServer, FixProtocol
from sxsuite.apps import Handler, ProcessApplication
from sxsuite.reaktor import Reaktor


class FixSink(Handler):
    """Simple process to eat all incoming messages."""
    def __init__(self, name):
        self.connection = None
        self.path = name
        self.fd = None

    def setup(self, connection):
        """We are not interested in writing back."""
        pass

    def handle(self, data):
        self._open()
        if self.fd is not None:
            self.fd.write(str(data))
            self.fd.flush()
        return None

    def finish(self):
        """Here we would do what ever needed when stopping."""
        pass

    def _open(self):
        if self.fd is None:
            try:
                self.fd = open(self.path, "a+")
            except IOError, e:
                print "IOError: ", str(e)


def get_session(args, reaktor, protocol):
    if args[0] == "client":
        app = FixClient(reaktor, protocol, name=args[0])
        app.set_conf('sender_comp_id', 'ASIDE')
        app.set_conf('target_comp_id', 'BSIDE')
    else:
        app = FixServer(reaktor, protocol, name=args[0])
        app.set_conf('sender_comp_id', 'BSIDE')
        app.set_conf('target_comp_id', 'ASIDE')

    app.set_conf('heartbeat_interval', 20)
    app.set_conf('login_wait_time', 30)
    app.set_conf('resend_mode', 'GAPFILL')
    return app

def main(args):

    logging.basicConfig(level=logging.DEBUG)

    reaktor = Reaktor()
    protocol = FixProtocol(version='4.4')

    process = ProcessApplication(reaktor, FixSink('sink.dat'), name='fixsink')
    session = get_session(args, reaktor, protocol)

    process.linkdown(session)
    session.linkup(process)

    session.start(('localhost', 2000))
    process.start()
    save_path = args[0] + '.state'
    reaktor.run([(session.state, save_path)])

if __name__ == "__main__":
    main(sys.argv[1:])


