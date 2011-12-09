
import sys
import logging
import traceback
import urlparse
try:
    # from python >= 2.7 
    from importlib import import_module
except ImportError:
    def import_module(name):
        import sys
        __import__(name)
        return sys.modules[name]
        

import sxsuite.exc as exc
from sxsuite.fix import FixClient, FixProtocol, FixContext
from sxsuite.reaktor import Reaktor
from sxsuite.apps import ProcessApplication
##from chixhandler import ChixCaptureReport

_LOGGING_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
    }



class LoginValidator(object):
    
    def __init__(self, app, ses):
        self.application = app
        self.session = ses

    def login_hook(self, data):
        """Send data to application and return ``True`` of successfull login."""
        self.application.send(data)
        return True

    def exchandler(self, ex):
        logging.warning("Reaktor exception: %s", str(ex))


def make_app(expr):
    """Make handler application.

    Application expression is in format *module:expression*. Imports *module* and
    evaluates *expression* in *module* context. Returned object is target application
    for handling messages.
    """
    modname, expression = expr.split(':', 1)
    module = import_module(modname)
    obj = eval(expression, module.__dict__)
    return obj

def read_config(path):
    import ConfigParser
    parser = ConfigParser.SafeConfigParser()
    with open(path, 'r') as fp:
        parser.readfp(fp)
    return parser
    

def run_session(handler_expr, options):
    """Run FIX session.

    Loads message handler application from ``handler_expr``. Fix client session
    connects to ``net_url``, which is of form *//host:port* or *tls://host:port*.
    """
    net_url = ''
    ses_cf = {}
    app_cf = {}
    if options.config:
        cf = read_config(options.config)
        ses_cf.update(cf.items(options.name))
        app_cf.update(cf.items(options.appname))

    fix_version = ses_cf.get('fixversion', options.fixversion)
    net_url = ses_cf.get('destination', options.dest)
    store_url = ses_cf.get('message_store', options.messages)
    statepath = ses_cf.get('state_path', options.statepath)

    if not net_url:
        logging.error("No target address defined")
        sys.exit(1)
        
    r = urlparse.urlparse(net_url)
    if r.netloc:
        addr, port = r.netloc.split(':')
        netaddr = (addr, int(port))
        use_tls = r.scheme == 'tls'
    else:
        logging.error("Illegal target address. Must be [tls:]//<host>:<port>")
        sys.exit(1)

    
    reaktor = Reaktor()
    protocol = FixProtocol(version=fix_version)

    target = make_app(handler_expr)
    app = ProcessApplication(reaktor, target, name=options.name)

    ses = FixClient(reaktor, protocol, name=options.name, store_url=store_url)

    for key, val in ses_cf.items():
        if key in ['heartbeat_interval', 'login_wait_time']:
            ses.set_conf(key, int(val))
        elif key in ['reset_seqno']:
            ses.set_conf(key, bool(val))
        else:
            ses.set_conf(key, val)

    for key, val in app_cf.items():
        app.set_conf(key, val)
    
    if options.sender:
        ses.set_conf('sender_comp_id', options.sender)
    if options.target:
        ses.set_conf('target_comp_id', options.target)
    if options.resend:
        ses.set_conf('resend_mode', options.resend)
    if options.reset:
        ses.set_conf('reset_seqno', options.reset)
    if not ses.get_conf('heartbeat_interval'):
        ses.set_conf('heartbeat_interval', options.heartbeat)
    if not ses.get_conf('login_wait_time'):
        ses.set_conf('login_wait_time', 30)

    app.linkdown(ses)
    ses.linkup(app)
    # overload session login validator
    validator = LoginValidator(app, ses)
    ses.login_hook = validator.login_hook

    ses.start(netaddr)
    app.start()

    savelist = []
    if statepath:
        ses.state.restore(statepath)
        savelist = [(ses, statepath)]

    reaktor.run(savelist=savelist, exc_handler=validator.exchandler)
    

def main():

    import optparse
    parser = optparse.OptionParser(
        usage='%prog [options] target handler_expression')
    parser.add_option('-D', '--daemon', default=False, action="store_true",
                      help='Run as daemon')
    parser.add_option('-H', '--heartbeat', default=30,
                      help='Heartbeat seconds')
    parser.add_option('-S', '--sender', default='',
                      help='Sender Company ID')
    parser.add_option('-T', '--target', default='',
                      help='Target Company ID')
    parser.add_option('-R', '--resend', default='',
                      help='Resend mode')
    parser.add_option('-r', '--reset', default=False, action="store_true",
                      help='Reset message seqno at logon')
    parser.add_option('-f', '--fixversion', default='4.4',
                      help='Fix Protocol version')
    parser.add_option('-s', '--statepath', default='',
                      help='Fix Session state store')
    parser.add_option('-m', '--messages', default='',
                      help='Fix Session message store URL')
    parser.add_option('-l', '--log', default='',
                      help='Logging destination file')
    parser.add_option('-v', '--verbose', default='INFO',
                      help='Logging verbosity level (DEBUG,INFO,WARNING,ERROR)')
    parser.add_option('-c', '--config', default='',
                      help='Configuration file')
    parser.add_option('-n', '--name', default='fixsession',
                      help='Session name (section in configuration file)')
    parser.add_option('-A', '--appname', default='application',
                      help='Application name (section in configuration file)')
    parser.add_option('-d', '--dest', default='',
                      help='Destination address')

    options, args = parser.parse_args()
    if not args or len(args) < 1:
        parser.print_help()
        sys.exit(2)

    handler_expr = args[0]

    log_level = _LOGGING_LEVELS.get(options.verbose, "WARNING")
    logging.basicConfig(level=log_level)

    if options.daemon:
        import daemon
        context = daemon.daemonContext()
        with context:
            run_session(handler_expr, options)
    else:
        run_session(handler_expr, options)


if __name__ == "__main__":
    main()


