import asyncio
import logging
import argparse
import os
import random
import socket
import aioconsole
import asyncudp
import sys


class TrackerUDPClient:
    def __init__(self,
                 announce_uri,
                 loop=None):
        self.logger = logging.getLogger(__name__)
        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()

        tracker_host, tracker_port = announce_uri.split(':')
        tracker_port = int(tracker_port)
        self.server_addr = tracker_host, tracker_port

        self.sock = None
        self.token = None

        self.tcp_peer = PeerTCPClient(tracker_client=self)
        self.get_input_task = None

    async def start(self):
        sock = await asyncudp.create_socket(remote_addr=self.server_addr)
        self.sock = sock
        first_hand = 'Hi, Tracker'
        sock.sendto(first_hand.encode())
        print("first handshake message sent")
        data, addr = await sock.recvfrom()
        print(f"got the token from {addr}")
        self.token = data.decode()
        self.tcp_peer.token = self.token
        if self.token:
            self.loop.create_task(self.send_heartbeat())
            self.get_input_task = self.loop.create_task(self.get_input())

    async def send_heartbeat(self):
        while True:
            hb = f'{self.token}%%hBeat'
            self.sock.sendto(hb.encode())
            await asyncio.sleep(5)

    async def stop(self):
        try:
            socket.close(1)
        except:
            print('client is closed. goodbye!')

    async def get_input(self):
        while True:
            question = await aioconsole.ainput('What can i Do for you?\n')

            if not question.startswith('peer'):
                self.logger.error('INVALID COMMEND, Wait 5 seconds')
                await asyncio.sleep(5)
                continue

            q_arr = '$$$ $$$'
            try:
                q_arr = question.split(' ')
            except:
                pass

            if q_arr[1] == 'share':
                file_name = q_arr[2]
                file_size = os.path.getsize(file_name)
                listen_address = q_arr[3]
                listen_address_arr = q_arr[3].split(':')
                share_req = f'{self.token}%%share%%{file_name}%%{file_size}%%{listen_address}'
                self.sock.sendto(share_req.encode())
                self.tcp_peer.file_name = file_name
                self.logger.info(
                    f'file {file_name} with size {file_size} shared to the tracker, Wait 5 seconds for next order')
                self.loop.create_task(
                    asyncio.start_server(self.tcp_peer.start_seeding, listen_address_arr[0], listen_address_arr[1]))
                self.get_input_task.cancel()
                self.logger.info(
                    f'peer {self.token} is a seeder. input is closed.')


            elif q_arr[1] == 'get':
                file_name = q_arr[2]
                file_size = os.path.getsize(file_name)
                listen_address = q_arr[3]
                share_req = f'{self.token}%%get%%{file_name}%%{file_size}%%{listen_address}'
                self.sock.sendto(share_req.encode())
                self.logger.info(
                    f'request for file {file_name} with size {file_size} has sent to the tracker')
                ans, ans_address = await self.sock.recvfrom()
                ans_arr = ans.decode().split("%%")
                if ans_arr[1] == 'nofile':
                    self.logger.error(
                        f'file {file_name} with size {file_size} is not available in the torrent')
                else:
                    peers_with_file = ans_arr[1].split('@@')
                    peers_with_file.remove(peers_with_file[len(peers_with_file) - 1])
                    self.logger.info('Peers with this file:')
                    print(peers_with_file)

                    count = 0
                    for p in peers_with_file:
                        self.logger.info(str(count) + ' ' + p + str('\n'))
                        count = count + 1
                    self.logger.info('choosing on of them random to get it')
                    try:
                        rand = random.randint(0, count - 1)
                    except:
                        rand = 0
                    chosen_peer = peers_with_file[rand]
                    address = chosen_peer.split(' ')
                    address_arr = address[len(address) - 1].split(':')
                    print(address_arr)
                    self.tcp_peer.wanted_address = listen_address
                    self.tcp_peer.file_name = file_name
                    self.loop.create_task(
                        self.tcp_peer.start_receiving(address_arr[0], address_arr[1])
                    )
            await asyncio.sleep(5)


class PeerTCPClient:
    def __init__(self, loop=None, tracker_client=None):
        self.logger = logging.getLogger(__name__)
        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()

        self.is_seeder = False
        self.file_name = None
        self.token = None

        self.wanted_address = None
        self.tracker_client = tracker_client

    async def start_seeding(self, reader, writer):
        global file
        self.is_seeder = True
        self.logger.info(f"seeding mode. waiting for a peer to request")

        data = await asyncio.wait_for(reader.read(4096), timeout=10.0)

        if data is None:
            self.logger.error(f"an error happened during receiving {self.file_name}")
            return

        if data.decode().split('%%')[1] != self.file_name:
            self.logger.error(f"an error happened during receiving {self.file_name}")
            return

        message = data.decode()
        msg_arr = message.split('%%')
        self.logger.info(f"peer {msg_arr[0]} has requested for the file {msg_arr[1]}")
        try:
            file = open(self.file_name, "r")
        except:
            try:
                file = open(self.token + '-' + self.file_name, "r")
            except:
                self.logger.info(f"couldn't find the file {msg_arr[1]}")
                return


        msg = file.read()
        writer.write(msg.encode())
        self.logger.info(f"file {msg_arr[1]} has been sent to the peer {msg_arr[0]}")

        ack = await reader.read(1024)
        ack_msg = ack.decode()
        if ack_msg == f'{msg_arr[0]}%%thanksforthefile':
            self.logger.info(f"peer {msg_arr[0]} has successfully received the file {msg_arr[1]}")

    async def start_receiving(self, address, port):
        reader, writer = await asyncio.open_connection(address, port)
        writer.write(f'{self.token}%%{self.file_name}'.encode())

        data = await asyncio.wait_for(reader.read(4096), timeout=10.0)

        if data is None:
            self.logger.error(f"an error happened during receiving {self.file_name}")
            return

        message = data.decode()
        f = open(self.token + '-' + self.file_name, "w+")
        f.write(message)
        self.logger.info(f"file {self.file_name} has been received")
        writer.write(f'{self.token}%%thanksforthefile'.encode())
        wanted_address = self.wanted_address.split(':')
        self.tracker_client.get_input_task.cancel()

        file_size = os.path.getsize(self.file_name)
        share_req = f'{self.token}%%seed%%{self.file_name}%%{file_size}%%{self.wanted_address}'
        self.tracker_client.sock.sendto(share_req.encode())

        self.logger.info(
            f'peer {self.token} is a seeder. input is closed.')
        self.loop.create_task(asyncio.start_server(self.start_seeding, wanted_address[0], wanted_address[1]))


def setup_logging():
    logger = logging.getLogger(__name__)
    formatter = logging.Formatter(
        '%(asctime) -15s - %(levelname) -8s - %(message)s')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def main():
    parser = argparse.ArgumentParser(description='UDP tracker')
    parser.add_argument(
        'tracker_uri', metavar='URI',
        help='The tracker URI.')

    args = parser.parse_args()
    setup_logging()

    loop = asyncio.get_event_loop()
    client = TrackerUDPClient(args.tracker_uri)
    loop.create_task(client.start())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print()
        loop.run_until_complete(client.stop())


if __name__ == '__main__':
    main()
