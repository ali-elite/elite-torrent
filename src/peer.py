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
        self.file_logger = None

        self.tcp_peer = PeerTCPClient(tracker_client=self)

        self.is_seeder = False

    async def start(self):
        sock = await asyncudp.create_socket(remote_addr=self.server_addr)
        self.sock = sock
        first_hand = 'Hi, Tracker'
        sock.sendto(first_hand.encode())
        self.logger.info("First handshake message sent to the tracker")

        data, addr = await sock.recvfrom()
        self.logger.info(f"Got the token from the tracker at {addr}")

        self.token = data.decode()
        self.tcp_peer.token = self.token
        if self.token:
            self.loop.create_task(self.send_heartbeat())
            self.loop.create_task(self.get_input())
            self.file_logger = self.set_logger()

    def set_logger(self):
        logger = logging.getLogger(f'{self.token}-logger')
        formatter = logging.Formatter(
            '%(asctime) -15s - %(levelname) -8s - %(message)s')
        handler = logging.FileHandler(f'peer-logs/{self.token}.log')
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    async def send_heartbeat(self):
        while True:
            hb = f'{self.token}%%hBeat'
            self.sock.sendto(hb.encode())
            # too much log
            # self.file_logger.info(f"sending heartbeat")
            await asyncio.sleep(2)

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

            if self.is_seeder and q_arr[1] != 'request':
                self.logger.error('SORRY WE ARE JUST SEEDING NOW, YOU CAN JUST ASK FOR LOGS, Wait 5 seconds')
                await asyncio.sleep(5)
                continue

            if q_arr[1] == 'request':
                f = open(f"peer-logs/{self.token}.log", "r")
                print('you have requested for the request logs. here is your response:')
                print(f.read())


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

                self.file_logger.info(
                    f'file {file_name} with size {file_size} shared to the tracker')

                self.loop.create_task(
                    asyncio.start_server(self.tcp_peer.start_seeding, listen_address_arr[0], listen_address_arr[1]))
                self.is_seeder = True


            elif q_arr[1] == 'get':
                file_name = q_arr[2]
                file_size = os.path.getsize(file_name)
                listen_address = q_arr[3]
                share_req = f'{self.token}%%get%%{file_name}%%{file_size}%%{listen_address}'
                self.sock.sendto(share_req.encode())

                self.logger.info(
                    f'request for file {file_name} with size {file_size} has sent to the tracker')
                self.file_logger.info(
                    f'request for file {file_name} with size {file_size} has sent to the tracker')

                ans, ans_address = await self.sock.recvfrom()
                ans_arr = ans.decode().split("%%")
                if ans_arr[1] == 'nofile':

                    self.logger.error(
                        f'file {file_name} with size {file_size} is not available in the torrent')

                    self.file_logger.error(
                        f'file {file_name} with size {file_size} is not available in the torrent')

                else:
                    peers_with_file = ans_arr[1].split('@@')
                    peers_with_file.remove(peers_with_file[len(peers_with_file) - 1])
                    self.logger.info('Peers with this file:')
                    self.file_logger.info(f'Peers with the file {file_name} that tracker sent:')

                    count = 0
                    for p in peers_with_file:
                        self.logger.info(str(count) + ' ' + p + str('\n'))
                        self.file_logger.info(str(count) + ' ' + p + str('\n'))

                        count = count + 1
                    self.logger.info('choosing on of them random to get it')
                    try:
                        rand = random.randint(0, count - 1)
                    except:
                        rand = 0
                    chosen_peer = peers_with_file[rand]

                    self.file_logger.info(f'peer number {rand} has chosen randomly')

                    address = chosen_peer.split(' ')
                    address_arr = address[len(address) - 1].split(':')
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
            self.logger.error(f"an error happened during receiving {self.file_name} : timeout")
            self.tracker_client.file_logger.error(f"an error happened during receiving {self.file_name} : timeout")
            return

        if data.decode().split('%%')[1] != self.file_name:
            self.logger.error(f"an error happened during receiving {self.file_name} : wrong name")
            self.tracker_client.file_logger.error(f"an error happened during receiving {self.file_name} : wrong name")
            return

        message = data.decode()
        msg_arr = message.split('%%')
        self.logger.info(f"peer {msg_arr[0]} has requested for the file {msg_arr[1]}")
        self.tracker_client.file_logger.info(f"peer {msg_arr[0]} has requested for the file {msg_arr[1]}")

        try:
            file = open(self.file_name, "r")
        except:
            try:
                file = open(self.token + '-' + self.file_name, "r")
            except:
                self.logger.error(f"couldn't find the file {msg_arr[1]}")
                self.tracker_client.file_logger.error(f"couldn't find the file {msg_arr[1]}")
                return


        msg = file.read()
        writer.write(msg.encode())
        self.logger.info(f"file {msg_arr[1]} has been sent to the peer {msg_arr[0]}")
        self.tracker_client.file_logger.info(f"file {msg_arr[1]} has been sent to the peer {msg_arr[0]}")

        ack = await reader.read(1024)
        ack_msg = ack.decode()
        if ack_msg == f'{msg_arr[0]}%%thanksforthefile':
            self.logger.info(f"peer {msg_arr[0]} has successfully received the file {msg_arr[1]}")
            self.tracker_client.file_logger.info(f"peer {msg_arr[0]} has successfully received the file {msg_arr[1]}")

    async def start_receiving(self, address, port):
        reader, writer = await asyncio.open_connection(address, port)
        writer.write(f'{self.token}%%{self.file_name}'.encode())

        data = await asyncio.wait_for(reader.read(4096), timeout=10.0)

        if data is None:
            self.logger.error(f"an error happened during receiving {self.file_name} :timeout")
            self.tracker_client.file_logger.error(f"an error happened during receiving {self.file_name} :timeout")
            return

        message = data.decode()
        f = open(self.token + '-' + self.file_name, "w+")
        f.write(message)

        self.logger.info(f"file {self.file_name} has been received")
        self.tracker_client.file_logger.info(f"file {self.file_name} has been received")


        writer.write(f'{self.token}%%thanksforthefile'.encode())
        wanted_address = self.wanted_address.split(':')
        self.is_seeder = True

        file_size = os.path.getsize(self.file_name)
        share_req = f'{self.token}%%seed%%{self.file_name}%%{file_size}%%{self.wanted_address}'
        self.tracker_client.sock.sendto(share_req.encode())

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
