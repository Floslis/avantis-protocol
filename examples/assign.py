#!/usr/bin/env python3
"""Minimal client for the Avantis native protocol (TCP 51321 + UDP heartbeat).
Reads and sets the assign of one input channel to one aux mix.

  python3 assign.py DESK-IP CHANNEL AUX            → show current state
  python3 assign.py DESK-IP CHANNEL AUX on|off     → set it

⚠️ This changes your desk. Try it on an unused channel, outside of shows.
Mono aux only in this example. See README for stereo aux and the formula."""
import socket, sys, threading, time

TAG = b"\x01\xf4"  # our own 2-byte tag; replies are addressed to it


def messages(buf):
    """Split a byte stream into F0 … F7 messages."""
    while (a := buf.find(b"\xf0")) >= 0 and (e := buf.find(b"\xf7", a)) >= 0:
        yield bytes(buf[a:e + 1])
        del buf[:e + 1]


def send(s, handle, param, data):
    s.sendall(b"\xf0\x00\x00" + handle + TAG + param.to_bytes(2, "big") + len(data).to_bytes(2, "big") + data + b"\xf7")


ip, channel, aux = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
wanted = sys.argv[4] if len(sys.argv) > 4 else None
param = 0x4550 + (channel - 1) * 56 + (aux - 1)  # assign: input channel → mono aux

# 1. Connect and announce our UDP port; the desk answers with its own UDP port
s = socket.create_connection((ip, 51321), timeout=5)
u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
u.bind(("", 0))
port = u.getsockname()[1].to_bytes(2, "big")
s.sendall(b"\xe0\x00\x04\x01\x03" + port + b"\xe7" + b"\xe0\x00\x04\x04\x03" + port + b"\xe7")

# 2. Look up the object „Input Mixer“ by name → handle
name = b"Input Mixer\x00"
s.sendall(b"\xf0\x00\x01\x00\x00" + TAG + b"\x00\x04" + len(name).to_bytes(2, "big") + name + b"\xf7")

buf, handle, state, udp_target = bytearray(), None, None, None
s.settimeout(1)
end = time.time() + 5
while time.time() < end and state is None:
    try:
        d = s.recv(65536)
    except socket.timeout:
        continue
    if udp_target is None and (k := d.find(b"\xe0\x00\x04\x02\x03")) >= 0:
        udp_target = (ip, int.from_bytes(d[k + 5:k + 7], "big"))

        # 3. Heartbeat: one UDP packet per second, otherwise the desk shows „Internal Error“ and drops us
        def heartbeat():
            while True:
                u.sendto(b"\xe0\x00\x01\x03\xe7", udp_target)
                time.sleep(1)
        threading.Thread(target=heartbeat, daemon=True).start()
    buf += d
    for m in messages(buf):
        if handle is None and m[1] == 0 and m[3:5] == TAG and m[5:11] == b"\x00\x00\x00\x02\x00\x02":
            handle = m[11:13]
            # 4. Subscribe to the parameter → the desk sends its current value and every change
            send(s, handle, 0x0006, b"\x00\x00" + TAG + param.to_bytes(2, "big") * 2 + b"\x00\xff")
        elif handle and len(m) == 13 and m[3:7] == TAG + handle and int.from_bytes(m[7:9], "big") == param:
            state = bool(m[11])

if state is None:
    sys.exit("No answer. Right IP? Network MIDI/control enabled?")
print(f"Channel {channel} → Aux {aux}: assign {'ON' if state else 'OFF'}")
if wanted in ("on", "off"):
    send(s, handle, param, b"\x01" if wanted == "on" else b"\x00")
    time.sleep(0.5)
    print(f"Set to {wanted.upper()}")
