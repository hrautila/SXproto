
import logging
import signal
import pickle

from multiprocessing import Process
import sxsuite.exc as exc
from sxsuite.session import Session, Client
from sxsuite.protocol import LineProtocol
from sxsuite.apps import Application, Pipe
from sxsuite.reaktor import Reaktor
from sxsuite.transport import ConnectedTransport

class SessionApp(Application):
    def __init__(self, transport):
        Application.__init__(self, None, transport=transport)
        
    def send(self, data):
        """Forward data upstream."""
        try:
            self.transport.socket.send(pickle.dumps(data))
        except Exception, ex:
            logging.debug("socket send error: %s", str(ex))
            raise ex

    def event_readable(self, transport):
        """Read data and push downstream."""
        # this is not a socket really
        data = self.transport.socket.recv()
        self.received(data)


class SessionConnector(object):

    class SessionRunner(object):
        def __init__(self, SessionClass, config):
            self.reaktor = None
            self.app = None
            self.session = None
            self._SessionClass = SessionClass
            self._config = config

        def _run(self, conn, args):
            self.reaktor = Reaktor()
            parent_link = ConnectedTransport(self.reaktor, conn)
            self.app = SessionApp(parent_link)

            self.session = self._SessionClass(self.reaktor)
            for key, val in self._config.items():
                self.session.set_conf(key, val)
            self.session.linkup(self.app)
            self.app.linkdown(self.session)
            self.app.start()
            self.session.start(args)
            signal.signal(signal.SIGTERM, self.reaktor.sigterm)
            save_path = self._config.get('session_state_file', '')
            savelist = []
            if save_path:
                savelist = [(self.session, save_path)]
            self.reaktor.run(savelist=savelist, exc_handler=self._exc_handler)
            
        def __call__(self, conn, args):
            self._run(conn, args)

        def _sigterm(self, signo, frame):
            self.reaktor.stop()

        def _exc_handler(self, ex):
            if isinstance(ex, exc.SessionError):
                self.app.send(ex)
                return True
            return False

    def __init__(self, SessionClass, config):
        self._SessionClass = SessionClass
        self._config = config
        self.conn = None

    def open(self, args):
        self.conn, child = Pipe(duplex=True)
        self._process = Process(target=SessionConnector.SessionRunner(self._SessionClass, self._config),
                                args=(child, args))
        self._process.start()

    def close(self):
        self._process.terminate()
        self._process.join(1)

    def recv(self):
        s = self.conn.recv()
        obj = pickle.loads(s)
        if isinstance(obj, Exception):
            raise obj
        return obj
    
    def send(self, data):
        self.conn.send(data)

    def fileno(self):
        return self.conn.fileno()



if __name__ == "__main__":
    class LineClient(Client):
        def __init__(self, reaktor, name=''):
            Client.__init__(self, reaktor, LineProtocol(), name=name)
        
    def main(args):
        logging.basicConfig(level=logging.DEBUG)
        cl = SessionConnector(LineClient, {})
        cl.open(('localhost', int(args[0])))
        try:
            while True:
                data = cl.recv()
                print '** ', data
                cl.send(data)
        except KeyboardInterrupt:
            pass
        except Exception, se:
            print '**', type(se), se.errno

        cl.close()

    import sys
    main(sys.argv[1:])


