import pathlib
import pytest
import tempfile
import time

from openocd import OpenOCD

@pytest.fixture(scope="module")
def openocd_jtag_nucleo_l4r5zi():
    config_args = [
        # use the RICEProbe cmsis-dap interface
        'source [find interface/cmsis-dap.cfg]',
        'cmsis_dap_vid_pid 0xFFFE 0xFFD1',
        # testing just the jtag transport here
        'transport select jtag',
        # target is a stm32l4r5zitx
        'source [find target/stm32l4x.cfg]',
        # use hardware reset
        'reset_config srst_only srst_nogate connect_assert_srst'
    ]
    with OpenOCD(config_args) as openocd:
        # ensure the target is reset and initialized, since we connected under reset
        openocd.send(b'reset init')
        yield openocd

@pytest.fixture(scope="module")
def rtt_nucleo_l4r5zi(openocd_jtag_nucleo_l4r5zi):
    openocd = openocd_jtag_nucleo_l4r5zi
    openocd.send(b'resume')
    rtt = openocd.enable_rtt()
    # make sure we can send data and receive the shell prompt
    assert(rtt.send(b'\n\n') == 2)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)
    yield rtt

def test_flash_read(openocd_jtag_nucleo_l4r5zi):
    openocd = openocd_jtag_nucleo_l4r5zi
    # start in a halted state
    openocd.send(b'halt')
    assert(b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'))

    # read out from a flash bank, to make sure we can transfer significant amounts of data
    with tempfile.NamedTemporaryFile() as file:
        path = pathlib.Path(file.name).as_posix().encode('ascii')
        # openocd flash read will fail if python is still holding the file open
        file.close()
        assert(b'wrote 4096 bytes' in openocd.send(b'flash read_bank 0 %b 0 4096' % (path)))

    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

def test_manipulate_memory(openocd_jtag_nucleo_l4r5zi, rtt_nucleo_l4r5zi):
    openocd = openocd_jtag_nucleo_l4r5zi
    rtt = rtt_nucleo_l4r5zi
    # start in a running state
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

    # make sure we can send data and receive the shell prompt
    assert(rtt.send(b'\n') == 1)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)

    # get the address of a global volatile variable
    assert(rtt.send(b'test var\n') == 9)
    address = rtt.expect_regex(rb'int \'var\' address: (0x[0-9a-fA-f]{1,8})').groups[0]
    value = rtt.expect_regex(rb'int \'var\' value: (\d{1,10})').groups[0]
    assert(value == b'0')

    # perform read-write-verify with openocd
    assert(b'0' in openocd.send(b'mrw %b' % (address)))
    openocd.send(b'mww %b 1234567890' % (address))
    assert(b'1234567890' in openocd.send(b'mrw %b' % (address)))

    # make sure that the shell reads the same value now
    assert(rtt.send(b'test var\n') == 9)
    value = rtt.expect_regex(rb'int \'var\' value: (\d{1,10})').groups[0]
    assert(value == b'1234567890')

    # add a watchpoint to the above variable
    openocd.send(b'halt')
    assert(b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'))
    openocd.send(b'wp %b 4 a' % (address))
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

    # now trigger the watchpoint and make sure the processor halts
    assert(rtt.send(b'\n') == 1)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)
    assert(rtt.send(b'test setvar 1\n') == 14)
    # halt might not happen instantly
    end = time.time() + 0.5
    while time.time() < end:
        if b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'):
            break
    assert(b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'))
    # remove the watchpoint
    openocd.send(b'rwp %b' % (address))
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

def test_breakpoint(openocd_jtag_nucleo_l4r5zi, rtt_nucleo_l4r5zi):
    openocd = openocd_jtag_nucleo_l4r5zi
    rtt = rtt_nucleo_l4r5zi
    # start in a running state
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

    # make sure we can send data and receive the shell prompt
    assert(rtt.send(b'\n') == 1)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)

    # get the address of the test function
    assert(rtt.send(b'test fn\n') == 8)
    address = rtt.expect_regex(rb'fn address: (0x[0-9a-fA-f]{1,8})').groups[0]

    # set a breakpoint for this function
    openocd.send(b'halt')
    assert(b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'))
    openocd.send(b'bp %b 2 hw' % (address))
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

    # trigger the breakpoint and make sure the processor halts
    assert(rtt.send(b'\n') == 1)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)
    assert(rtt.send(b'test fn\n') == 8)
    # halt might not happen instantly
    end = time.time() + 0.5
    while time.time() < end:
        if b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'):
            break
    assert(b'halted' in openocd.send(b'$_CHIPNAME.cpu curstate'))
    # remove the watchpoint
    openocd.send(b'rbp all')
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

def test_rtt_transfer(openocd_jtag_nucleo_l4r5zi, rtt_nucleo_l4r5zi):
    openocd = openocd_jtag_nucleo_l4r5zi
    rtt = rtt_nucleo_l4r5zi
    # start in a running state
    openocd.send(b'resume')
    assert(b'running' in openocd.send(b'$_CHIPNAME.cpu curstate'))

    # make sure we can read a large dump of data over the rtt interface
    assert(rtt.send(b'test dump\n') == 10)
    assert(rtt.expect_bytes(b'0x0000018f') is not None)
    assert(rtt.expect_bytes(b'target:~$ ') is not None)
