#!/usr/bin/env python3
"""Find Avantis desks on the local network by listening to their UDP announcements (port 51319).
Sends nothing. Usage: python3 discover.py"""
import json, re, socket, time

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
if hasattr(socket, "SO_REUSEPORT"):  # so Director / Mixing Station can listen at the same time
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
s.bind(("", 51319))
s.settimeout(0.5)
found, end = {}, time.time() + 4
while time.time() < end:
    try:
        data, (ip, _) = s.recvfrom(2048)
    except socket.timeout:
        continue
    if not data.startswith(b"AH_UF"):
        continue
    parts = [p.decode("latin1") for p in data.split(b"\x00") if p]
    m = re.search(rb"\{.*\}", data)
    version = ".".join(json.loads(m.group()).get("V", [])) if m else ""
    found[ip] = (parts[2] if len(parts) > 2 else "?", version)
for ip, (model, version) in found.items():
    print(f"{ip}  {model}  firmware {version}")
if not found:
    print("Nothing heard. Same network/VLAN as the desk?")
