import sys
from time import time
HEADER_SIZE = 12

class RtpPacket:
    header = bytearray(HEADER_SIZE)

    def __init__(self):
        pass

    def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
        """Encode the RTP packet with the specified parameters."""
        
        # Use an integer timestamp (seconds since epoch)
        timestamp = int(time()) 
        
        # 1. First two bytes (0 and 1)
        # Byte 0: V (2 bits) | P (1 bit) | X (1 bit) | CC (4 bits)
        # Byte 1: M (1 bit) | PT (7 bits)
        self.header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc
        self.header[1] = (marker << 7) | pt

        # 2. Sequence Number (2 bytes: 2 and 3) - 16 bits
        # Copy a 16-bit integer seqnum into 2 bytes (network byte order/big-endian):
        self.header[2] = (seqnum >> 8) & 0xFF
        self.header[3] = seqnum & 0xFF

        # 3. Timestamp (4 bytes: 4, 5, 6, 7) - 32 bits
        # Copy a 32-bit integer timestamp into 4 bytes:
        self.header[4] = (timestamp >> 24) & 0xFF
        self.header[5] = (timestamp >> 16) & 0xFF
        self.header[6] = (timestamp >> 8) & 0xFF
        self.header[7] = timestamp & 0xFF
        
        # 4. SSRC (4 bytes: 8, 9, 10, 11) - 32 bits
        # Copy a 32-bit integer ssrc into 4 bytes:
        self.header[8] = (ssrc >> 24) & 0xFF
        self.header[9] = (ssrc >> 16) & 0xFF
        self.header[10] = (ssrc >> 8) & 0xFF
        self.header[11] = ssrc & 0xFF
        
        # 5. Set the payload
        self.payload = payload

    def decode(self, byteStream):
        """Decode the RTP packet."""
        self.header = bytearray(byteStream[:HEADER_SIZE])
        self.payload = byteStream[HEADER_SIZE:]

    # --- Decoder methods for client side (already implemented) ---
    def version(self):
        """Return RTP version."""
        return int(self.header[0] >> 6)

    def seqNum(self):
        """Return sequence number."""
        seqNum = self.header[2] << 8 | self.header[3]
        return int(seqNum)

    def timestamp(self):
        """Return timestamp."""
        timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
        return int(timestamp)

    def payloadType(self):
        """Return payload type."""
        pt = self.header[1] & 127
        return int(pt)

    def getPayload(self):
        """Return payload."""
        return self.payload

    def getPacket(self):
        """Return RTP packet."""
        return self.header + self.payload