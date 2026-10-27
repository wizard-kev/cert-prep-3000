# CCST Cybersecurity (100-160) | Chapter 2: Network Security Devices

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 2 (user-supplied list, plus user-approved additions in Section E)
**File version:** v2 | **Domain tags:** provisional until checked against Cisco's blueprint (CIA/threats fit 1.0 Essential Security Principles; NAC, honeypot, wireless, and devices fit 2.0 Basic Network Security Concepts)

**Usage:** IDs (`C02-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions.

---

## A. Security fundamentals, NAC, and deception

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C02-01 | CIA triad | Confidentiality (no unauthorized disclosure), Integrity (no unauthorized change), Availability (accessible when needed) | Classify a scenario by which property is violated: eavesdropping = C, tampering = I, outage = A |
| C02-02 | Internal threats | Originate from people/systems inside the organization (employees, contractors) | Already have legitimate access; may be malicious or accidental |
| C02-03 | External threats | Originate outside the organization | Must first get past the perimeter |
| C02-04 | Network Access Control (NAC) | Decides whether a device/user may join the network based on identity and policy | Gatekeeper at connection time; enforces policy |
| C02-05 | Posture assessment | Checks a device's health/compliance (patches, antivirus, configuration) before or during access | Non-compliant devices are denied, quarantined, or remediated |
| C02-06 | Guest network | Separate, restricted network segment for visitors | Isolated from internal resources; internet-only access is typical |
| C02-07 | Persistent vs nonpersistent agents | Persistent = software permanently installed on the endpoint; nonpersistent = temporary, removed after the assessment | Permanent vs temporary; nonpersistent suits guests/BYOD |
| C02-08 | Honeypot | Decoy system that lures attackers to detect and study them | No legitimate use, so any interaction is suspicious |

## B. Wireless network types, devices, and principles

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C02-09 | WPAN | Wireless personal area network; very short range (e.g., Bluetooth) | Smallest scale: one person's devices |
| C02-10 | WLAN | Wireless local area network; Wi-Fi within a building or campus | The common enterprise/home wireless scale |
| C02-11 | WMAN | Wireless metropolitan area network; spans a city or large area | Between WLAN and WWAN in scale |
| C02-12 | WWAN | Wireless wide area network; cellular-style coverage over large regions | Largest scale; carrier-provided |
| C02-13 | Wireless access point (WAP) | Connects wireless clients to the wired network | Bridge between wireless and wired; the infrastructure-side device |
| C02-14 | Wireless network access card | Client-side adapter that lets a device connect wirelessly | Client-side hardware; the WAP is infrastructure-side |
| C02-15 | Wireless antennae | Radiate and receive signal; omnidirectional vs directional | Omnidirectional = all directions, wider coverage; directional = focused beam, longer reach |
| C02-16 | Independent BSS (ad hoc) | Devices connect directly to each other with no AP | No AP; peer-to-peer |
| C02-17 | Basic Service Set (BSS) | One AP plus its associated clients; the basic wireless building block | Single AP coverage area |
| C02-18 | Infrastructure BSS | BSS in which clients communicate through the AP | Contrast with ad hoc: traffic flows via the AP |
| C02-19 | Service Set ID (SSID) | The name identifying a wireless network | A network *name*, not a security control |
| C02-20 | Extended Service Set (ESS) | Two or more BSSs linked by a wired distribution system under one SSID | Enables roaming across multiple APs |

## C. Wi-Fi channels, standards, and performance

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C02-21 | Nonoverlapping channels: 2.4GHz band | Only three nonoverlapping channels (1, 6, 11 in the US) | Few channels, so crowding is common |
| C02-22 | 5GHz band (802.11ac) | 802.11ac operates in 5GHz only, with many more nonoverlapping channels | 5GHz only; more channels, less crowding |
| C02-23 | 2.4GHz / 5GHz (802.11n) | 802.11n operates in either band (dual-band) | The standard that spans both bands |
| C02-24 | Wi-Fi 6 (802.11ax) | Newer standard focused on efficiency in dense environments (e.g., OFDMA) | Gains are efficiency and capacity, not just raw speed |
| C02-25 | Interference | Signal degradation from other wireless sources or overlapping channels | Co-channel/overlap and non-Wi-Fi sources (e.g., microwaves, Bluetooth); 2.4GHz is more exposed |
| C02-26 | Wi-Fi range and speed comparisons | 2.4GHz = longer range, better penetration, slower; 5GHz = faster, shorter range | The range-vs-speed trade-off between bands |

## D. Wireless security

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C02-27 | Authentication and encryption | Authentication verifies who connects; encryption protects the data | Identity vs confidentiality of traffic; separate functions |
| C02-28 | WEP | Original wireless security using RC4 with a short initialization vector | Broken and obsolete; never acceptable |
| C02-29 | WPA | Interim replacement for WEP using TKIP | Stopgap that ran on legacy hardware; superseded by WPA2 |
| C02-30 | WPA2 | Uses AES-CCMP; the long-standing standard | AES replaces TKIP/RC4; Personal uses a shared passphrase |
| C02-31 | WPA2 Enterprise | WPA2 with 802.1X authentication against a RADIUS server | Individual credentials per user, not one shared key |
| C02-32 | 802.11i | IEEE standard for wireless security that WPA2 implements | The standard; WPA2 is the Wi-Fi Alliance certification of it |
| C02-33 | WPA3 | Current generation; stronger handshake and protections than WPA2 | Replaces the PSK handshake; resists offline password guessing |
| C02-34 | WPA3-Personal | Passphrase-based WPA3 using SAE (Simultaneous Authentication of Equals) | SAE instead of WPA2's PSK handshake |
| C02-35 | WPA3-Enterprise | WPA3 with 802.1X/RADIUS and stronger cryptography (optional 192-bit mode) | Enterprise = per-user authentication; 192-bit suite is for high-security use |

## E. Network security devices (user-approved additions)

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C02-36 | Firewall | Permits or denies traffic between networks based on rules | Boundary enforcement by policy |
| C02-37 | Stateless (packet-filtering) firewall | Judges each packet alone on IP, port, protocol | No memory of sessions; every packet needs a matching rule |
| C02-38 | Stateful firewall | Tracks connection state and allows return traffic for established sessions | Remembers sessions; contrast with stateless |
| C02-39 | Next-generation firewall (NGFW) | Adds application awareness, deep packet inspection, and integrated IPS | Sees applications, not just ports |
| C02-40 | Host-based vs network-based firewall | Host-based runs on one endpoint; network-based sits at a network boundary | Protects one device vs protects a whole segment |
| C02-41 | IDS | Monitors traffic (typically a passive copy) and alerts on suspicious activity | Detects and alerts only; does not block |
| C02-42 | IPS | Sits inline and blocks detected malicious traffic | Acts on threats; inline placement means a failure can disrupt traffic |
| C02-43 | Signature-based vs anomaly-based detection | Signature = match known patterns; anomaly = flag deviation from a baseline | Signature misses novel attacks; anomaly catches them but raises more false positives |
| C02-44 | Proxy server / web filter | Intermediary that makes requests for clients and can filter content | Works at the application level on behalf of clients |

---

## Chapter-specific question angles
- Scenario → choose the wireless security protocol and justify it
- Given a site description (range, density, speed need) → choose the band or standard
- Scenario → choose the right device (stateless vs stateful firewall, IDS vs IPS, proxy)
- Neighbor discrimination: BSS vs IBSS vs ESS; persistent vs nonpersistent; WPA2-Personal vs WPA2-Enterprise; IDS vs IPS
- "Which is NOT" on wireless types, security protocols, or device functions
