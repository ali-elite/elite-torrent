# Elite-Torrent 🌊📡

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![Asyncio](https://img.shields.io/badge/Asynchronous-IO-blue?style=for-the-badge)](https://docs.python.org/3/library/asyncio.html)
[![Networking](https://img.shields.io/badge/Networking-P2P-red?style=for-the-badge)](https://en.wikipedia.org/wiki/Peer-to-peer)

**Elite-Torrent** is a custom Peer-to-Peer (P2P) file-sharing network implementation developed for the Computer Networks course at Sharif University of Technology. It utilizes a centralized tracker for peer discovery and direct peer-to-peer TCP connections for high-performance file transfer.

## 🏗️ Architecture

The system follows a classic Torrent architecture:

### 1. The Tracker (`tracker.py`)
- **Protocol**: UDP (User Datagram Protocol)
- **Role**: Coordinates the network and maintains a registry of available files and active peers.
- **Features**:
  - **Dynamic Registration**: Peers register via a handshake.
  - **Heartbeat Monitoring**: Periodically checks peer health to ensure network reliability.
  - **File Indexing**: Maps filenames and sizes to the addresses of peers holding them.
  - **Peer Discovery**: Responds to queries with a list of available seeders.

### 2. The Peer (`peer.py`)
- **Protocol**: TCP (Transmission Control Protocol) for data, UDP for tracker communication.
- **Roles**: Acts as both a **Seeder** (file provider) and a **Leecher** (file downloader).
- **Features**:
  - **Async Execution**: Built on `asyncio` for non-blocking concurrent connections.
  - **Dual-Stack Networking**: Handles tracker heartbeats while simultaneously serving/downloading files.
  - **Logging**: Comprehensive per-peer logging system for tracking requests and transfers.
  - **Randomized Discovery**: Automatically connects to random available peers for balanced network load.

## 🚀 Commands

Peers interact with the network through a CLI interface:

- `peer share <filename> <ip:port>`: Share a local file with the network and start seeding on the specified address.
- `peer get <filename> <local_size> <ip:port>`: Locate a file via the tracker, download it from an available peer, and then start seeding it to others.
- `peer request`: View the local session logs and transaction history.

## 🛠️ Tech Stack

- **Primary Language**: Python 3.x
- **Concurrency**: `asyncio`, `asyncudp`, `aioconsole`
- **Networking**: Socket programming (UDP/TCP)

---
*Sharif University of Technology - Computer Engineering Department*
