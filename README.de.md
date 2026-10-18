# Allen & Heath Avantis: Notizen zum Netzwerkprotokoll

[English](README.md) · **Deutsch**

Was das Avantis im Netz sagt und wie man ihm antwortet. Nachgebaut aus Mitschnitten von Mixing Station und vom Pult selbst, damit andere Werkzeuge bauen können, ohne bei null anzufangen.

> [!WARNING]
> **Inoffiziell und unvollständig.** Allen & Heath dokumentiert nur den Teil MIDI über TCP. Alles zum nativen Protokoll unten ist beobachtet, nicht spezifiziert. Es funktioniert an einem Avantis mit **Firmware V2.01 Rev. 97241**, kann bei anderen Versionen abweichen. **Außerhalb von Shows testen**, mit jemandem am Pult. Wer das Lebenszeichen falsch macht, bekommt am Pult **„Internal Error“** (in unseren Tests ohne Folgen für den Ton, trotzdem).

Diese Notizen stecken hinter **[avantis-talkback](https://github.com/Floslis/avantis-talkback)**, einem Tool, das das Assign eines Talkback-Kanals per Browser oder Softkey auf In-Ear-Mixe schaltet.

[![Unterstütze mich auf Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/floslist)

---

## Überblick

| Port | Weg | Dokumentiert | Wofür |
|---|---|---|---|
| **51319** | UDP-Broadcast, Pult → Netz | nein | das Pult meldet sich (Modell, Firmware) |
| **51320** | UDP-Broadcast, Pult → Netz | nein | das Pult sucht seine Erweiterungen (IP-Karten, GPIO, …) |
| **51321** | TCP + UDP | nein | natives Protokoll (Director, Mixing Station): alles, auch **Assign** |
| **51325** | TCP | **ja** | MIDI über TCP: Fader, Mutes, Send-Pegel, Namen, Szenen, Mute-Gruppen |

## 1. Das Pult finden (UDP 51319)

Etwa 1,5-mal pro Sekunde sendet das Pult so ein Paket an alle:

```
AH_UFV2 \0 Bridge Find \0 Avantis Console \0 {"V":["2","0","1"], "N":"Bridge"} \0
```

Die Absender-IP ist das Pult, im JSON steht die Firmware (`2.0.1`). Einfach zuhören, senden muss man nichts. Beispiel: [`examples/discover.py`](examples/discover.py).

## 2. MIDI über TCP (Port 51325, offiziell)

Dokumentiert im *Avantis MIDI TCP Protocol*. Was hier genutzt wird:

- **Basiskanal N** (am Pult eingestellt, Standard 12) und vier weitere: N = Eingänge, N+2 = Aux-Mixe, N+4 = Mute-Gruppen, DCAs und mehr
- **Name abfragen:** `F0 00 00 1A 50 10 01 00 <Kanal> 01 <Nr> F7` → Antwort `… <Kanal> 02 <Nr> <Name, 8 Byte> F7`
  - Mono-Aux 1 … 24 = `Nr` `0x00` …, **Stereo-Aux 1 … 12 = `0x40` …** auf Kanal N+2
  - **Nur vorhandene Mixe antworten.** So lässt sich die Mix-Konfiguration einfach erkennen
- **Mute-Gruppen:** Note auf Kanal N+4, Note `0x45 + Gruppe` (Gruppe 1 = `0x46`), Anschlagstärke `7F` = gemutet, `3F` = nicht gemutet, danach eine Note mit `00`. Das Pult sendet das, wenn sich eine Mute-Gruppe ändert, und nimmt es zum Setzen an. Nützlicher Trick: Ein Softkey auf einer **leeren Mute-Gruppe** ist ein Knopf mit LED, den man lesen und setzen kann
- **Send-Pegel** Eingang → Aux: `F0 00 00 1A 50 10 01 00 <N> 0D <Eingang> <N+2> <Aux> <Pegel> F7` (`6B` ≈ 0 dB, `00` = −∞)
- **Per MIDI nicht möglich:** Eingang auf Aux oder Gruppe zuweisen, Send-Pegel zurücklesen, das pulteigene Talkback

## 3. Natives Protokoll (TCP 51321 + UDP)

### Aufbau der Nachrichten

Zwei Arten von Nachrichten im TCP-Strom:

| Beginn | Ende | Was |
|---|---|---|
| `E0` | `E7` | Sitzung (Anmeldung) |
| `F0` | `F7` | Daten |

Daten-Nachricht:

```
F0 00 <Art> <Ziel-Handle: 2 Byte> <Absender-Tag: 2 Byte> <Parameter: 2 Byte> <Länge: 2 Byte> <Daten> F7
```

- `Art` vom Client: `00` = setzen / abonnieren, `01` = Objekt per Name nachschlagen. In Antworten des Pults steht hier eine **Client-Nummer**, die sich je Sitzung ändert, also nicht vergleichen
- **Tag:** 2 Byte, frei gewählt (z. B. `01 F4`). Das Pult adressiert Antworten daran
- **Handle:** 2 Byte, die das Pult für ein Objekt vergibt (siehe Nachschlagen)

### Anmeldung

1. Einen UDP-Socket auf einem beliebigen lokalen Port öffnen
2. Per TCP `E0 00 04 01 03 <eigener UDP-Port, 2 Byte> E7` und `E0 00 04 04 03 <eigener UDP-Port> E7` senden
3. Das Pult antwortet `E0 00 04 02 03 <UDP-Port des Pults, 2 Byte> E7`

### Lebenszeichen ⚠️

**`E0 00 01 03 E7` jede Sekunde per UDP an den UDP-Port des Pults** schicken. Fehlt es, oder nennt man einen UDP-Port, auf dem niemand lauscht, zeigt das Pult **„Internal Error“** und trennt nach etwa 30 Sekunden.

Die TCP-Verbindung selbst ist still, solange sich am Pult nichts ändert. Das ist normal, Stille ist kein Abbruch.

### Objekt nachschlagen

Objekte werden per Klartext-Name angesprochen:

```
F0 00 01 00 00 <Tag> 00 04 <Namenslänge: 2 Byte> "Input Mixer" 00 F7
→ F0 00 <xx> <Tag> 00 00 00 02 00 02 <Handle: 2 Byte> F7
```

Mixing Station schlägt beim Start rund 2.000 Objekte nach, zum Beispiel `Input Mixer`, `Digital Attenuator Input Channel 62`, `Parametric EQ, Input Channel 83 - Intermediate`.

### Abonnieren

Pro Parameter, Anfang und Ende gleich:

```
F0 00 00 <Handle> <Tag> 00 06 00 0A 00 00 <Tag> <Param> <Param> 00 FF F7
```

Danach schickt das Pult den aktuellen Wert und jede Änderung:

```
F0 00 <xx> <Tag> <Handle> <Param> 00 01 <Wert> F7
```

### Wert setzen

```
F0 00 00 <Handle> <Tag> <Param> <Länge> <Wert> F7
```

### Input Mixer: Assign und Send-Pegel

| Was | Parameter | Wert |
|---|---|---|
| **Assign** Eingang → Mix | `0x4550 + (Kanal − 1) × 56 + Platz` | 1 Byte, `00` / `01` |
| Send-Pegel | Assign + `0x2A00` | 2 Byte, `0000` = −∞ |
| unbekannter Schalter (Pre/Post?) | Assign + `0x1500` | 1 Byte |

**Platz:** Mono-Aux *n* = *n* − 1. **Stereo-Aux *n* = (Zahl der Mono-Aux) + 2 × (*n* − 1)**, ein Stereo-Mix belegt zwei Plätze.

Beispiel Kanal 64 → Mono-Aux 1: `0x4550 + 63 × 56 + 0 = 0x5318`.

Vollständiges Beispiel in Python: [`examples/assign.py`](examples/assign.py).

## Was noch offen ist

- [ ] Stimmt die Regel für Stereo-Plätze bei anderen Mix-Konfigurationen? (bewiesen mit 12 Mono-Aux)
- [ ] Gruppen und Matrizen als Ziele
- [ ] Bedeutung von Assign + `0x1500`, genaue dB-Skala des Send-Pegels
- [ ] Die Talkback-Ziele des Pults selbst
- [ ] Andere Firmware als V2.01

**Du hast einen Mitschnitt oder einen anderen Aufbau?** Issues und Pull Requests sind sehr willkommen. So schneide ich mit: `tcpdump` auf dem Mac, auf dem Mixing Station läuft, dann eine Aktion nach der anderen und notieren, was ich geklickt habe.

## Unterstützen

Wenn dir diese Notizen ein Wochenende mit Mitschnitten sparen, freue ich mich über einen Kaffee. ☕

[![Unterstütze mich auf Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/floslist)

## Lizenz

[MIT](LICENSE) · Nicht mit Allen & Heath verbunden · Ein Projekt von **[FLOTECH](https://flotech.dev)**
