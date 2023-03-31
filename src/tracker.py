import argparse
import asyncio
import logging
import os
import string
import sys
import random
from datetime import datetime, timedelta

import aioconsole

DEFAULT_INTERVAL = 10


class EliteFile():
    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.logs = []
        self.seeders = {}
        self.logger = self.set_logger()

    def __str__(self):
        return f'FILE({self.name}, {self.size})'

    def __repr__(self):
        return str(self)

    def set_logger(self):
        logger = logging.getLogger(f'{self.name}-logger')
        formatter = logging.Formatter(
            '%(asctime) -15s - %(levelname) -8s - %(message)s')
        handler = logging.FileHandler(f'tracker-file-logs/{self.name}.log')
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger


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
        self.file_logger = logging.getLogger('main-tracker-logger')

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
            self.logger.info(f'client {response} has connected to the tracker!')
            self.file_logger.info(f'client {response} has connected to the tracker! request type: first handshake')


        else:
            rsp = data.decode()
            rsp_arr = rsp.split('%%')
            if rsp_arr[0][:10] not in self.server.peers or self.server.peers.get(rsp_arr[0][:10]) == 0:
                self.logger.warning('Invalid client')
                return

            elif rsp_arr[1].startswith('hBeat'):
                self.server.peers.update({rsp_arr[0]: datetime.now()})
                # too much log
                # self.file_logger.info(f'client {rsp_arr} heartbeat ')
                return

            elif rsp_arr[1].startswith('share'):
                file_name = rsp_arr[2]
                file_size = rsp_arr[3]
                listen_address = rsp_arr[4]
                file = EliteFile(name=file_name, size=file_size)
                file.seeders.update({rsp_arr[0]: listen_address})
                self.server.files.append(file)
                self.logger.info(f'client {rsp_arr[0]} shared the file {file_name} in the torrent')
                file.logger.info(f'client {rsp_arr[0]} shared the file {file_name} in the torrent')
                self.file_logger.info(f'client {rsp_arr[0]} shared the file {file_name} in the torrent')
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
                self.logger.info(f'client {rsp_arr[0]} received the file {file_name}'
                                 f' successfully and is seeding the file in the torrent')
                file.logger.info(f'client {rsp_arr[0]} received the file {file_name}'
                                 f' successfully and is seeding the file in the torrent')
                self.file_logger.info(f'client {rsp_arr[0]} received the file {file_name}'
                                      f' successfully and is seeding the file in the torrent')
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
                    self.logger.info(f'file list sent to the client {rsp_arr[0]}')
                    the_file.logger.info(f'file list sent to the client {rsp_arr[0]}')
                    the_file.logger.info(ans)
                else:
                    ans = f'{rsp_arr[0]}%%nofile'
                    self.logger.warning('file was not available!')
                    self.file_logger.warning(f'peer {rsp_arr[0]} has requested for a non-exist file')
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
        self.file_logger = logging.getLogger('main-tracker-logger')
        self.file_logger.info('tracker server started')

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
        self.get_input_task = self.loop.create_task(self.get_input())

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
                                f.logger.info(f'seeder {p} disconnected')
                        self.logger.info(f'peer {p} disconnected and we removed it from the tracker.')
                        self.file_logger.info(f'seeder {p} disconnected')
            await asyncio.sleep(DEFAULT_INTERVAL)

    async def get_input(self):
        while True:
            question = await aioconsole.ainput('What can i Do for you?\n')
            if question == 'request logs':

                f = open("tracker-logs/tracker-logs.log", "r")
                print('you have requested for the request logs. here is your response:')
                print(f.read())

            elif question == 'file_logs_all':
                print('you have requested for all files logs. here is your response:')
                for f in os.listdir("tracker-file-logs/"):
                    f = open(f'tracker-file-logs/{f}', "r")
                    print(f.read())

            elif question.startswith('file_logs>'):
                q_arr = question.split('>')
                try:
                    print(f'you have requested for the file {q_arr[1]} logs. here is your response:')
                    f = open(f"tracker-file-logs/{q_arr[1]}.log", "r")
                    print(f.read())
                except:
                    print(f"there isn't a log for such a file called {q_arr[1]} in the torrent")


            await asyncio.sleep(5)


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


def setup_file_logging():
    logger = logging.getLogger('main-tracker-logger')
    formatter = logging.Formatter(
        '%(asctime) -15s - %(levelname) -8s - %(message)s')
    handler = logging.FileHandler('tracker-logs/tracker-logs.log')
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
    file_logger = setup_file_logging()
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
