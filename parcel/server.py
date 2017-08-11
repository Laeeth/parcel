# import signal
import urlparse
from cparcel import lib
import logging
import time


# Logging
log = logging.getLogger('server')


class Server(object):

    def start(self, proxy_host, proxy_port, remote_uri):
        """

        """
        # Signal handling for external calls
        # signal.signal(signal.SIGINT, signal.SIG_DFL)

        p = urlparse.urlparse(remote_uri)
        assert p.scheme, 'No url scheme specified'
        port = p.port or {'https': '443', 'http': '80'}[p.scheme]
        log.info('Binding proxy server {0}:{1} -> {2}:{3}'.format(
            proxy_host, proxy_port, p.hostname, port))
        proxy = lib.udt2tcp_start(
            str(proxy_host), str(proxy_port), str(p.hostname), str(port))
        assert proxy == 0, 'Proxy failed to start'

        while True:
            time.sleep(99999999)  # Block because udt2tcp_start is non-blocking
