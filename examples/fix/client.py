
import sys
import logging
import traceback
import urlparse
import ssl

import sxsuite.exc as exc
from sxsuite.fix import FixClient, FixServer, FixProtocol, FixContext
from sxsuite.apps import Handler, ProcessApplication
from sxsuite.timer import add_timer
from sxsuite.reaktor import Reaktor
from sxsuite.transport import SSLContext
from sxsuite.fix.fix44 import NewOrderSingle

class FixSource(Handler):
    """Simple process to create messages."""
    def __init__(self, name):
        self.connection = None
        self.path = name
        self.fd = None
        self.tid = None
        self.ctx = FixContext(version='4.4')

    def setup(self, connection):
        """We are not interested in writing back."""
        self.connection = connection
        self.tid = add_timer(30, self.new_message)
        logging.debug("timer added %d", self.tid)

    def handle(self, data, connection):
        self._open()
        if self.fd is not None:
            self.fd.write(str(data))
            self.fd.flush()
        return None

    def finish(self, connection):
        """Here we would do what ever needed when stopping."""
        pass

    def new_message(self):

        logging.debug("generating new message")

        message = NewOrderSingle(self.ctx)
        message.ClOrdID = "Oid-%04d" % random.randrange(1000, 3000)
        message.Side = random.choice(['1', '0'])
        message.OrdType = "1"
        message.Symbol = "FOO"
        message.Currency = "EUR"
        message.SecurityID = "ISIN_000"
        message.OrderQty = random.randrange(50, 100)
        message._64 = str(datetime.now())
        new_message = message.to_message(FixHeader(self.ctx))
        logging.debug("writing: %s", str(new_message))
        self.connection.send(new_message)

        # re-arm generator
        self.tid = add_timer(30, self.new_message)
        logging.debug("timer re-armed: %d", self.tid)

    def _open(self):
        if self.fd is None:
            try:
                self.fd = open(self.path, "a+")
            except IOError, e:
                print "IOError: ", str(e)

class FixSink(Handler):
    """Simple process to eat all incoming messages."""
    def __init__(self, name):
        self.connection = None
        self.path = name
        self.fd = None

    def setup(self, connection):
        """We are not interested in writing back."""
        pass

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



class SSLClientContext(SSLContext):
    def verify(self, sock):
        cert = sock.getpeercert()
        logging.debug('peer cert: %s', cert)
        logging.debug('cipher info: %s', sock.cipher())
        return True

def exchandler(ex):
    logging.warning("Reaktor exception: %s", str(ex))

def main(argv):

    import getopt
    short_opts = 'S:T:h:C:s:t:r:M:'
    long_opts = ["sender=", "target=", "heartbeat=",
                 "ca=", "state=", "type=", "resend=", "store="]

    try:
        opts, args = getopt.getopt(argv, short_opts, long_opts)
    except getopt.GetoptError, e:
        print str(e)
        sys.exit(1)

    sender_id = 'ASIDE'
    target_id = 'BSIDE'
    hb_interval = 30
    cafile = ''
    netaddr = ('localhost', 2000)
    save_path = 'client.state'
    use_tls = False
    file_name = 'sink.dat'
    app_type = 'sink'
    resend = 'GAPFILL'
    store_url = ''

    for o, a in opts:
        if o in ["-S", "--sender"]:
            sender_id = a
        elif o in ["-T", "--target"]:
            target_id = a
        elif o in ["-h", "--heartbeat"]:
            hb_interval = int(a)
        elif o in ["-C", "--ca"]:
            cafile = a
        elif o in ["-s", "--state"]:
            save_path = a
        elif o in ["-t", "--type"]:
            app_type = a
        elif o in ["-r", "--resend"]:
            resend = a
        elif o in ["-M", "--store"]:
            store_url = a
        

    if args:
        r = urlparse.urlparse(args.pop(0))
        if r.netloc:
            addr, port = r.netloc.split(':')
            netaddr = (addr, int(port))
            use_tls = r.scheme == 'tls'
        else:
            print "target address: [tls:]//<host>:<port>"
            sys.exit(1)

    if args:
        file_name = args.pop(0)

    logging.basicConfig(level=logging.DEBUG)

    reaktor = Reaktor()
    protocol = FixProtocol(version='4.4')

    if app_type == 'sink':
        target = FixSink(file_name)
    else:
        target = FixSource(app_type)

    process = ProcessApplication(reaktor, target, name=app_type)
    ses = FixClient(reaktor, protocol, name='client', store_url=store_url)

    ses.set_conf('sender_comp_id', sender_id)
    ses.set_conf('target_comp_id', target_id)
    ses.set_conf('heartbeat_interval', hb_interval)
    ses.set_conf('login_wait_time', 30)
    ses.set_conf('resend_mode', resend)

    process.linkdown(ses)
    ses.linkup(process)

    if use_tls:
        ses.ssl_context(SSLClientContext(cert_reqs=ssl.CERT_OPTIONAL,
                                         ca_certs=cafile,
                                         ssl_version=ssl.PROTOCOL_TLSv1))

    ses.start(netaddr)
    process.start()
    ses.state.restore(save_path)
    reaktor.run(savelist=[(ses, save_path)], exc_handler=exchandler)

if __name__ == "__main__":
    main(sys.argv[1:])


