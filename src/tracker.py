import argparse
import asyncio
import logging
import string
import sys
import random
from datetime import datetime, timedelta

DEFAULT_INTERVAL = 10

class EliteFile():
    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.logs = []
        self.seeders = {}

    def __str__(self):
        return f'FILE({self.name}, {self.size})'
    def __repr__(self):
        return str(self)


def get_random_string(length):
    # choose from all lowercase letter
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str


class UdpTrackerServer(asyncio.Protocol):
    def __init__(self, server):
        self.server = server
        self.logger = server.logger
        self.connection_lost_received = asyncio.Event()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.connection_lost_received.set()

    def error_received(self, exc):
        self.logger.info('Error received:'.format(exc))

    def datagram_received(self, data, addr):
        if data.decode() == 'Hi, Tracker':
            response = get_random_string(10)
            self.server.peers.update({response: datetime.now()})
            self.transport.sendto(response.encode(), addr)
            self.logger.info(f'client { response } joined!')

        else:
            rsp = data.decode()
            rsp_arr = rsp.split('%%')
            if rsp_arr[0][:10] not in self.server.peers or self.server.peers.get(rsp_arr[0][:10]) == 0:
                self.logger.warning('Invalid client')
                return

            elif rsp_arr[1].startswith('hBeat'):
                self.server.peers.update({rsp_arr[0]: datetime.now()})
                return

            elif rsp_arr[1].startswith('share'):
                file_name = rsp_arr[2]
                file_size = rsp_arr[3]
                listen_address = rsp_arr[4]
                file = EliteFile(name=file_name, size=file_size)
                file.seeders.update({rsp_arr[0]: listen_address})
                self.server.files.append(file)
                self.logger.warning('file shared!')
                return

            elif rsp_arr[1].startswith('seed'):
                file_name = rsp_arr[2]
                file_size = rsp_arr[3]
                listen_address = rsp_arr[4]

                file = None
                for f in self.server.files:
                    if f.name == file_name:
                        file = f
                        break

                file.seeders.update({rsp_arr[0]: listen_address})
                self.server.files.append(file)
                self.logger.warning('file seeded!')
                return

            elif rsp_arr[1].startswith('get'):
                the_file = None
                for file in self.server.files:
                    if file.name == rsp_arr[2]:
                        the_file = file
                        break
                if the_file:
                    ans = f'{rsp_arr[0]}%%'
                    for idd, l_address in the_file.seeders.items():
                        if l_address != 'dis':
                            ans = ans + f'peer {idd} with listen address {l_address}@@'
                    self.logger.warning(f'file list sent to the client {rsp_arr[0]}')
                else:
                    ans = f'{rsp_arr[0]}%%nofile'
                    self.logger.warning('file was not available!')
                self.transport.sendto(ans.encode(), addr)
                return

            else:
                self.logger.warning('Invalid message')
                return

class TrackerServer:
    def __init__(self,
                 local_addr=('127.0.0.1', 6881),
                 interval=DEFAULT_INTERVAL,
                 loop=None):
        self.local_addr = local_addr
        self.interval = interval
        self.peers = {}
        self.files = []

        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()

        self.transport = None
        self.proto = None
        self.started_up = asyncio.Event()
        self.logger = logging.getLogger(__name__)
        self.is_closed = False

        self.loop.create_task(self.heartbeat_check())

    async def start(self):
        self.transport, self.proto = await self.loop.create_datagram_endpoint(
            lambda: UdpTrackerServer(self),
            local_addr=self.local_addr)

        self.local_addr = self.transport._sock.getsockname()
        self.logger.info('Started listening on {}:{}.'.format(*self.local_addr))
        self.started_up.set()
        self.is_closed = False

    async def stop(self):
        self.transport.close()
        self.is_closed = True
        await self.proto.connection_lost_received.wait()
        self.logger.info('Tracker stopped.')

    async def heartbeat_check(self):
        while not self.is_closed:
            for p, last_modified in self.peers.items():
                if last_modified != 0:
                    if last_modified <= datetime.now() - timedelta(seconds=DEFAULT_INTERVAL):
                        self.peers[p] = 0
                        for f in self.files:
                            if p in f.seeders.keys():
                                f.seeders[p] = 'dis'
                        self.logger.info(f'peer {p} has been removed.')
            await asyncio.sleep(DEFAULT_INTERVAL)


def end_point(v):
    if ':' in v:
        host, port = v.split(':')
    else:
        host, port = v, 8000

    if host == '':
        host = '127.0.0.1'

    if port == '':
        port = '8000'

    port = int(port)

    return host, port


def setup_logging():
    logger = logging.getLogger(__name__)
    formatter = logging.Formatter(
        '%(asctime) -15s - %(levelname) -8s - %(message)s')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def main():
    parser = argparse.ArgumentParser(description='UDP tracker.')
    parser.add_argument(
        '--address', '-address', default='127.0.0.1:8000', type=end_point,
        metavar='HOST:PORT',
        help='The address to bind to. Defaults to 127.0.0.1:8000')

    args = parser.parse_args()
    logger = setup_logging()
    loop = asyncio.get_event_loop()

    tracker = TrackerServer(local_addr=args.address,
                            loop=loop)
    asyncio.ensure_future(tracker.start())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print()
        loop.run_until_complete(tracker.stop())


if __name__ == '__main__':
    main()
