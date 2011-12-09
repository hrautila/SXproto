
import sys
import logging
import traceback
import urlparse

import sxsuite.exc as exc
from sxsuite.fix import FixClient, FixServer, FixProtocol
from sxsuite.apps import Handler, ProcessApplication
from sxsuite.reaktor import Reaktor
from sxsuite.transport import SSLContext

class FixSink(Handler):
    """Simple process to eat all incoming messages."""
    def __init__(self, name):
        self.connection = None
        self.path = name
        self.fd = None
        self.config = None

    def setup(self, connection, config):
        """We are not interested in writing back."""
        logging.info("setup application ...")
        self.config = config
        for k, v in self.config.items():
            logging.info( "appconfig: %s = %s", k, v)


    def handle(self, data, connection):
        self._open()
        if self.fd is not None:
            self.fd.write(str(data))
            self.fd.flush()
        return None

    def finish(self, connection):
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

class SSLServerContext(SSLContext):
    def verify(self, sock):
        cert = sock.getpeercert()
        logging.debug('peer cert: %s', cert)
        return True

def main(args):

    target = ('localhost', 2000)
    use_tls = False

    if args:
        r = urlparse.urlparse(args.pop(0))
        if r.netloc:
            addr, port = r.netloc.split(':')
            target = (addr, int(port))
            use_tls = r.scheme == 'tls'
        else:
            print "target address: [tls:]//<host>:<port>"
            sys.exit(1)

    logging.basicConfig(level=logging.DEBUG)

    reaktor = Reaktor()
    protocol = FixProtocol(version='4.4')

    process = ProcessApplication(reaktor, FixSink('sink.dat'), name='fixsink')
    session = get_session(args, reaktor, protocol)

    process.linkdown(session)
    session.linkup(process)

    if use_tls:
        session.ssl_context(SSLServerContext())

    session.start(target)
    process.start()
    save_path = args[0] + '.state'
    reaktor.run([(session.state, save_path)])

if __name__ == "__main__":
    main(sys.argv[1:])


