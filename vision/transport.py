"""UDP transport: receive messages from Godot, send results back."""
from __future__ import annotations

import logging
import socket
from typing import Any, Dict, List, Tuple

from .protocol import decode_message, encode_message

log = logging.getLogger(__name__)


class UdpTransport:
    def __init__(self, listen_addr: Tuple[str, int], godot_addr: Tuple[str, int]):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(listen_addr)
        self._sock.setblocking(False)
        self.godot_addr = godot_addr

    @property
    def listen_port(self) -> int:
        return self._sock.getsockname()[1]

    def poll(self) -> List[Dict[str, Any]]:
        """Return all messages that have arrived since the last call (never blocks)."""
        messages: List[Dict[str, Any]] = []
        while True:
            try:
                data, _ = self._sock.recvfrom(65535)
            except BlockingIOError:
                break
            except ConnectionResetError:
                # Windows reports an earlier send to a closed port this way; harmless.
                continue
            try:
                messages.append(decode_message(data))
            except (ValueError, UnicodeDecodeError) as exc:
                log.warning("dropping malformed datagram: %s", exc)
        return messages

    def send(self, msg: Dict[str, Any]) -> None:
        self._sock.sendto(encode_message(msg), self.godot_addr)

    def close(self) -> None:
        self._sock.close()
