from ctypes import cdll, create_string_buffer
lib = cdll.LoadLibrary('lparcel.so')
import logging
import atexit
import sys
from functools import wraps
import threading

from const import (
    # Lengths
    LEN_CONTROL, LEN_TOKEN, LEN_PAYLOAD_SIZE,
    # Control messages
    CNTL_EXIT, CNTL_DOWNLOAD, CNTL_HANDSHAKE,
    # States
    STATE_IDLE,
)

import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

log = logging.getLogger('parcel')
log.setLevel(logging.DEBUG)
log.propagate = False
formatter = logging.Formatter(
    '[%(asctime)s][%(name)10s][%(levelname)7s] %(message)s')
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(formatter)
log.addHandler(handler)


def vec(val):
    return val if hasattr(val, '__iter__') else [val]


def state_method(states):
    """Enter a new state

    :param states:
        A list of str or single str specifying the states that are
        valid preceeding this one

    """

    def wrapper(func, *args, **kwargs):
        @wraps(func)
        def f(self, *args, **kwargs):
            assert self.state in vec(states), \
                'Moving from state <{}> to <{}> is invalid'.format(
                    self.state, func.__name__)
            self.state = func.__name__
            log.debug('Entering state: {}'.format(self.state))
            func(self, *args, **kwargs)
            log.debug('exiting state: {}'.format(self.state))
        return f
    return wrapper


class Server(object):

    def __init__(self):
        """
        Creates a new udpipeClient instance from shared object library
        """

        self.server = lib.new_server()
        atexit.register(self.close)

    def start(self, host='localhost', port=9000):
        log.info('Starting server at {}:{}'.format(host, port))
        lib.server_start(self.server, str(host), str(port))
        log.info('Server ready at {}:{}'.format(host, port))
        self.listen()

    def close(self):
        lib.server_close(self.server)

    def server_thread(self, thread):
        logging.info('New client: {}'.format(thread))

    def listen(self):
        threads = []
        while True:
            sthread = ServerThread(lib.server_next_client(self.server))
            t = threading.Thread(target=self.server_thread, args=(sthread,))
            t.daemon = True
            threads.append(t)
            t.start()


class ParcelThread(object):

    def __init__(self, instance, socket, close_func):
        """
        Creates a new udpipeClient instance from shared object library
        """

        atexit.register(self.close)
        self.instance = instance
        self.socket = socket
        self.close_func = close_func
        self.buff_len = 64000000
        self.buff = create_string_buffer(self.buff_len)
        self.state = STATE_IDLE
        log.info('New instance {}'.format(self))
        self.handshake()

    def __repr__(self):
        return '<{}, instance: {}, socket: {}>'.format(
            type(self).__name__, self.instance, self.socket)

    def read_size(self, size):
        buff = create_string_buffer(size)
        rs = lib.read_size(self.socket, buff, size)
        if (rs == -1):
            raise Exception('Unable to read from socket.')
        return buff.value

    def send_payload_size(self, size):
        buff = create_string_buffer(LEN_PAYLOAD_SIZE)
        buff.value = str(size)
        self.send(buff, LEN_PAYLOAD_SIZE)

    def read_payload_size(self):
        payload_size = int(self.read_size(LEN_PAYLOAD_SIZE))
        return payload_size

    def next_payload(self):
        payload_size = self.read_payload_size()
        return self.read_size(payload_size)

    def send_payload(self, payload, size):
        self.send_payload_size(size)
        self.send(payload, size)

    def read(self):
        while True:
            log.debug('Blocking read ...')
            rs = lib.read_data(self.socket, self.buff, self.buff_len)
            if rs < 0:
                raise StopIteration()
            log.debug('Read {} bytes'.format(rs))
            yield self.buff[:rs]

    def send(self, data, size=None):
        if size is None:
            size = len(data)
        lib.send_data(self.socket, data, size)

    def close(self):
        self.send_control(CNTL_EXIT)
        self.close_func(self.instance)

    def send_control(self, cntl):
        cntl_buff = create_string_buffer(LEN_CONTROL)
        cntl_buff.raw = cntl
        self.send(cntl_buff)

    def recv_control(self, expected=None):
        cntl = self.read_size(LEN_CONTROL)
        log.debug('CONTROL: {}'.format(ord(cntl)))
        if expected is not None and cntl not in vec(expected):
            raise RuntimeError('Unexpected control msg: {} != {}'.format(
                ord(cntl), ord(expected)))
        return cntl

    @state_method(STATE_IDLE)
    def handshake(self):
        self.send_control(CNTL_HANDSHAKE)
        self.recv_control(CNTL_HANDSHAKE)

    @state_method('handshake')
    def authenticate(self, *args, **kwargs):
        raise NotImplementedError()


class ServerThread(ParcelThread):

    def __init__(self, instance):
        super(ServerThread, self).__init__(
            instance=instance,
            socket=lib.sthread_get_socket(instance),
            close_func=lib.sthread_close,
        )
        self.authenticate()
        self.live = True
        while self.live:
            self.event_loop()

    def clientport(self):
        return lib.sthread_get_clientport(self.instance)

    def clienthost(self):
        return lib.sthread_get_clienthost(self.instance)

    @state_method('handshake')
    def recv_cmd(self):
        self.send_control(CNTL_HANDSHAKE)
        r = self.recv_control()
        assert r == CNTL_HANDSHAKE

    @state_method('handshake')
    def authenticate(self):
        token = self.next_payload()
        log.info('Connected with token: "{}"'.format(token))

    @state_method(['authenticate', 'event_loop'])
    def shut_down(self):
        log.info('Thread exiting cleanly.')
        self.live = False

    @state_method(['event_loop'])
    def download(self):
        file_id = self.next_payload()
        log.info('Download request: {}'.format(file_id))

    @state_method(['authenticate', 'event_loop', 'download'])
    def event_loop(self):
        switch = {
            CNTL_EXIT: self.shut_down,
            CNTL_DOWNLOAD: self.download,
        }
        cntl = self.recv_control()
        if cntl not in switch:
            raise RuntimeError('Unknown control code {}'.format(cntl))
        switch[cntl]()


class Client(ParcelThread):

    def __init__(self, token, host='localhost', port=9000):
        client = lib.new_client()
        log.info('Connecting to server at {}:{}'.format(host, port))
        lib.client_start(client, str(host), str(port))
        super(Client, self).__init__(
            instance=client,
            socket=lib.client_get_socket(client),
            close_func=lib.client_close,
        )
        self.authenticate(token)

    @state_method('handshake')
    def authenticate(self, token):
        self.send_payload(token, len(token))

    @state_method('authenticate')
    def download(self, uuid):
        self.send_control(CNTL_DOWNLOAD)
        self.send_payload(uuid, len(uuid))
