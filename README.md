# Allen & Heath Avantis: network protocol notes

**English** · [Deutsch](README.de.md)

What the Avantis says on the network, and how to talk back. Rebuilt from packet captures of Mixing Station and the desk itself, so others can build tools without starting from zero.

> [!WARNING]
> **Unofficial and incomplete.** Allen & Heath documents only the MIDI over TCP part. Everything about the native protocol below was observed, not specified. It works on an Avantis with **firmware V2.01 Rev. 97241**, but may differ on other versions. **Test outside of shows**, with someone at the desk. Getting the heartbeat wrong makes the desk show **"Internal Error"** (no effect on audio in our tests, but still).

These notes power **[allenheath-talkback](https://github.com/Floslis/allenheath-talkback)**, a tool that switches a talkback channel's assign to in-ear mixes from the browser or desk softkeys.

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/floslist)

---

## Overview

| Port | Transport | Documented | What for |
|---|---|---|---|
| **51319** | UDP broadcast, desk → network | no | the desk announces itself (model, firmware) |
| **51320** | UDP broadcast, desk → network | no | the desk looks for its peripherals (IP cards, GPIO, …) |
| **51321** | TCP + UDP | no | native protocol (Director, Mixing Station): everything, including **assign** |
| **51325** | TCP | **yes** | MIDI over TCP: faders, mutes, send levels, names, scenes, mute groups |

## 1. Finding the desk (UDP 51319)

About 1.5 times per second the desk broadcasts a packet like this:

```
AH_UFV2 \0 Bridge Find \0 Avantis Console \0 {"V":["2","0","1"], "N":"Bridge"} \0
```

The sender's IP is the desk, the JSON carries the firmware (`2.0.1`). Just listen, nothing needs to be sent. Example: [`examples/discover.py`](examples/discover.py).

## 2. MIDI over TCP (port 51325, official)

Documented in the *Avantis MIDI TCP Protocol*. The parts used here:

- **Base channel N** (set on the desk, default 12) plus four more: N = inputs, N+2 = aux mixes, N+4 = mute groups, DCAs and more
- **Name request:** `F0 00 00 1A 50 10 01 00 <ch> 01 <nr> F7` → reply `… <ch> 02 <nr> <name, 8 bytes> F7`
  - Mono aux 1 … 24 = `nr` `0x00` …, **stereo aux 1 … 12 = `0x40` …** on channel N+2
  - **Only mixes that exist answer.** That's an easy way to detect the mix configuration
- **Mute groups:** note on channel N+4, note `0x45 + group` (group 1 = `0x46`), velocity `7F` = muted, `3F` = unmuted, followed by a note with velocity `00`. The desk sends this when a mute group changes and accepts it to set one. Useful trick: a softkey on an **empty mute group** gives you a button with LED feedback you can read and set
- **Send level** input → aux: `F0 00 00 1A 50 10 01 00 <N> 0D <input> <N+2> <aux> <level> F7` (`6B` ≈ 0 dB, `00` = −∞)
- **Not possible via MIDI:** assigning an input to an aux or group, reading send levels back, the desk's own talkback

## 3. Native protocol (TCP 51321 + UDP)

### Message format

Two kinds of messages on the TCP stream:

| Start | End | What |
|---|---|---|
| `E0` | `E7` | session control (handshake) |
| `F0` | `F7` | data |

Data message:

```
F0 00 <class> <target handle: 2 bytes> <source tag: 2 bytes> <parameter: 2 bytes> <length: 2 bytes> <data> F7
```

- `class` from the client: `00` = set / subscribe, `01` = look up an object by name. In replies from the desk this byte is a **client number** that changes per session, so don't compare it
- **Tag:** 2 bytes you choose yourself (e.g. `01 F4`). The desk addresses replies to it
- **Handle:** 2 bytes the desk gives you for an object (see lookup)

### Handshake

1. Open a UDP socket on any local port
2. Over TCP send `E0 00 04 01 03 <your UDP port, 2 bytes> E7` and `E0 00 04 04 03 <your UDP port> E7`
3. The desk answers `E0 00 04 02 03 <desk UDP port, 2 bytes> E7`

### Heartbeat ⚠️

Send **`E0 00 01 03 E7` by UDP to the desk's UDP port once per second**. Without it, or if you announce a UDP port nobody listens on, the desk shows **"Internal Error"** and drops the connection after about 30 seconds.

The TCP connection itself is silent while nothing changes on the desk. That's normal, don't treat silence as a timeout.

### Looking up an object

Objects are addressed by plain-text name:

```
F0 00 01 00 00 <tag> 00 04 <name length: 2 bytes> "Input Mixer" 00 F7
→ F0 00 <xx> <tag> 00 00 00 02 00 02 <handle: 2 bytes> F7
```

Mixing Station looks up around 2,000 objects at start, for example `Input Mixer`, `Digital Attenuator Input Channel 62`, `Parametric EQ, Input Channel 83 - Intermediate`.

### Subscribing

Per parameter, start and end the same:

```
F0 00 00 <handle> <tag> 00 06 00 0A 00 00 <tag> <param> <param> 00 FF F7
```

The desk then sends the current value and every change:

```
F0 00 <xx> <tag> <handle> <param> 00 01 <value> F7
```

### Setting a value

```
F0 00 00 <handle> <tag> <param> <length> <value> F7
```

### Input Mixer: assign and send level

| What | Parameter | Value |
|---|---|---|
| **Assign** input → mix | `0x4550 + (channel − 1) × 56 + slot` | 1 byte, `00` / `01` |
| Send level | assign + `0x2A00` | 2 bytes, `0000` = −∞ |
| unknown switch (pre/post?) | assign + `0x1500` | 1 byte |

**Slot:** mono aux *n* = *n* − 1. **Stereo aux *n* = (number of mono aux) + 2 × (*n* − 1)**, a stereo mix takes two slots.

Example, channel 64 → mono aux 1: `0x4550 + 63 × 56 + 0 = 0x5318`.

Full example in Python: [`examples/assign.py`](examples/assign.py).

## What's still open

- [ ] Is the stereo slot rule right for other mix configurations? (proven with 12 mono aux)
- [ ] Groups and matrices as targets
- [ ] Meaning of assign + `0x1500`, exact dB scale of the send level
- [ ] The desk's own talkback destinations
- [ ] Firmware other than V2.01

**Got a capture or a different setup?** Issues and pull requests are very welcome. How I capture: `tcpdump` on the Mac running Mixing Station, then one action at a time with a note of what I clicked.

## Support

If these notes save you a weekend of packet captures, I'm happy about a coffee. ☕

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/floslist)

## License

Text: [CC BY-SA 4.0](LICENSE), share with credit and under the same license · Example code in [`examples/`](examples/): [AGPL-3.0](examples/LICENSE) · © 2026 Florian Hogrebe · earlier versions were MIT · Not affiliated with Allen & Heath · A project by **[FLOTECH](https://flotech.dev)**
