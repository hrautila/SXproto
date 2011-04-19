
import sys
import logging
import traceback
import random
from datetime import datetime

import sxsuite.exc as exc
from sxsuite.fix import FixClient, FixServer, FixProtocol, FixContext, FixHeader
from sxsuite.apps import Handler, ProcessApplication
from sxsuite.reaktor import Reaktor
from sxsuite.timer import add_timer, del_timer
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

    def handle(self, data):
        self._open()
        if self.fd is not None:
            self.fd.write(str(data))
            self.fd.flush()
        return None

    def finish(self):
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


def get_session(args, reaktor, protocol):
    if args[0] == "client":
        app = FixClient(reaktor, protocol, name=args[0])
        app.set_conf('sender_comp_id', 'ASIDE')
        app.set_conf('target_comp_id', 'BSIDE')
    else:
        app = FixServer(reaktor, protocol, name=args[0])
        app.set_conf('sender_comp_id', 'BSIDE')
        app.set_conf('target_comp_id', 'ASIDE')

    app.set_conf('heartbeat_interval', 60)
    app.set_conf('login_wait_time', 30)
    app.set_conf('resend_mode', 'GAPFILL')
    return app

def main(args):

    logging.basicConfig(level=logging.DEBUG)

    reaktor = Reaktor()
    protocol = FixProtocol(version='4.4')

    process = ProcessApplication(reaktor, FixSource('source.dat'), name='fixsource')
    session = get_session(args, reaktor, protocol)

    process.linkdown(session)
    session.linkup(process)

    save_path = args[0] + '.state'
    session.state.restore(save_path)

    session.start(('localhost', 2000))
    process.start()
    reaktor.run([(session.state, save_path)])

if __name__ == "__main__":
    main(sys.argv[1:])


