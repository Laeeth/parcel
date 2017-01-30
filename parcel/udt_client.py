from .client import Client
from .cparcel import lib

import logging
import urlparse

# Logging
log = logging.getLogger('client')


class UDTClient(Client):

    def __init__(self, proxy_host, proxy_port, verify=True,
                 external_proxy=False, *args, **kwargs):
        if not external_proxy:
            # Create a local UDT proxy that translates TCP to UDT
            self.start_proxy_server(proxy_host, proxy_port, remote_uri)

        super(UDTClient, self).__init__(*args, **kwargs)

    def construct_local_uri(self, proxy_host, proxy_port, remote_uri):
        """Given proxy settings and remote_uri, construct the uri where the
        proxy request will be sent

        """
        p = urlparse.urlparse(remote_uri)
        scheme = p.scheme or 'https'
        local_uri = '{}://{}:{}{}'.format(
            scheme, proxy_host, proxy_port, p.path)
        return local_uri

    def start_proxy_server(self, proxy_host, proxy_port, remote_uri):
        """Bind proxy.

        """

        p = urlparse.urlparse(remote_uri)
        port = p.port or 9000
        log.info('Binding proxy server {}:{} -> {}:{}'.format(
            str(proxy_host), str(proxy_port), str(p.hostname), str(port)))
        proxy = lib.tcp2udt_start(
            str(proxy_host), str(proxy_port), str(p.hostname), str(port))
        assert proxy == 0, 'Proxy failed to start'
