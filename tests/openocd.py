import shutil
import socket
import streamexpect
import subprocess
import time

class OpenOCD:
    TERM = b'\x1a'

    def __init__(self, config, exec=None, tcl_port=6666, rtt_port=7777):
        # openocd server initialization
        self.exec = exec if exec is not None else shutil.which('openocd')
        self.config = config
        self.tcl_port = tcl_port
        self.rtt_port = rtt_port
        self.process = None

        # socket for connection to openocd tcl interface
        self.ip = '127.0.0.1'
        self.tcl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcl_sock.settimeout(1.0)
        self.rtt_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # data buffering for server responses
        self.buffer = bytes()
        self.buffer_chunk = 1024

    def start(self):
        # startup the openocd server
        openocd_args = [self.exec]
        # make sure to use the expected port
        openocd_args.extend(['-c', f'tcl_port {self.tcl_port}'])
        for command in self.config:
            openocd_args.extend(['-c', command])
        self.process = subprocess.Popen(
            openocd_args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # connect over the tcl interface
        self.tcl_sock.connect((self.ip, self.tcl_port))
        # ensure we can send a command
        self.send(b'version')

    def __enter__(self):
        self.start()
        return self

    def close(self):
        try:
            # attempt to close nicely
            self.send(b'rtt server stop %i' % (self.rtt_port))
            self.send(b'shutdown')
            time.sleep(0.1)
        finally:
            # close connections and force server shutdown
            self.tcl_sock.close()
            self.rtt_sock.close()
            self.process.terminate()

    def __exit__(self, _type, _value, _traceback):
        self.close()

    def send(self, data):
        self.tcl_sock.send(data + self.TERM)
        # get and return response
        idx = -1
        while idx < 0:
            # read back in 1k chunks
            chunk = self.tcl_sock.recv(self.buffer_chunk)
            self.buffer += chunk
            # check for the terminator character
            idx = self.buffer.find(self.TERM)

        response = self.buffer[:idx]
        # strip the terminator character and prevoius response
        self.buffer = self.buffer[idx+1:]
        return response

    def enable_rtt(self, address=b'0x20000000', size=b'0x10000'):
        self.send(b'rtt setup %b %b "SEGGER RTT"' % (address, size))
        self.send(b'rtt start')
        if b'Channels:' not in self.send(b'rtt channels'):
            raise ValueError('failed to find rtt channels, initialization failed')
        self.send(b'rtt server start %i 0' % (self.rtt_port))
        
        self.rtt_sock.connect((self.ip, self.rtt_port))
        return streamexpect.wrap(self.rtt_sock)
