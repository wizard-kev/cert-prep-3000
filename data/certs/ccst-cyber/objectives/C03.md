# CCST Cybersecurity (100-160) | Chapter 3: IP, IPv6, and NAT

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 3 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 2.0 Basic Network Security Concepts; secure vs insecure protocol items also touch 1.0)

**Usage:** IDs (`C03-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See C01-xx / C02-xx" marks a cross-chapter link usable for mixed questions.

---

## A. Application layer protocols (DoD model)

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C03-01 | Telnet | Remote command-line access over TCP 23 | Cleartext, so credentials are exposed; insecure |
| C03-02 | SSH | Encrypted remote access over TCP 22 | The secure replacement for Telnet |
| C03-03 | FTP | File transfer over TCP 20/21 | Credentials and data in cleartext; reliable (TCP) |
| C03-04 | SFTP | File transfer tunneled through SSH (TCP 22) | Encrypted; not the same as FTP or TFTP |
| C03-05 | TFTP | Simple file transfer over UDP 69 | No authentication; used for config/firmware/boot files |
| C03-06 | SNMP | Network device monitoring and management (UDP 161; traps on 162) | v3 adds authentication and encryption; v1/v2c use community strings |
| C03-07 | HTTP | Web traffic over TCP 80 | Cleartext |
| C03-08 | HTTPS | HTTP protected by TLS over TCP 443 | Encrypted and authenticated; HTTP + TLS |
| C03-09 | NTP | Clock synchronization over UDP 123 | Consistent time matters for logs and certificates |
| C03-10 | DNS | Resolves names to IP addresses (port 53) | UDP for normal queries; TCP for large responses/zone transfers; see C01-13 |
| C03-11 | DHCP | Automatically assigns IP configuration (UDP 67 server / 68 client) | Dynamic assignment of address, mask, gateway, DNS; see C01-16 |
| C03-12 | BootP | Older predecessor of DHCP (UDP 67/68) | Static MAC-to-IP mapping; DHCP adds dynamic assignment |
| C03-13 | APIPA | Self-assigned 169.254.0.0/16 address when no DHCP server answers | Signals a DHCP failure; link-local only, no gateway |

## B. Host-to-host and Internet layer protocols

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C03-14 | TCP | Connection-oriented, reliable delivery (three-way handshake, sequencing, acknowledgments) | Reliability and ordering; see C01-10 |
| C03-15 | UDP | Connectionless, best-effort delivery | Low overhead, no delivery guarantee |
| C03-16 | TCP vs UDP usage, pros and cons | TCP for accuracy (web, email, file transfer); UDP for speed (voice, video, DNS queries) | Reliability vs speed/overhead trade-off |
| C03-17 | TCP/UDP port numbers | Identify the service: well-known 0-1023, registered 1024-49151, dynamic 49152-65535 | Clients use ephemeral source ports; servers listen on well-known ports |
| C03-18 | IP | Logical addressing and routing of packets | Connectionless and best-effort; carries no delivery guarantee |
| C03-19 | ICMP | Error reporting and diagnostics (ping, traceroute) | Control messages, not application data; see C01-09 |
| C03-20 | ARP | Resolves an IPv4 address to a MAC address on the local segment | Local subnet only; see C01-15 |

## C. IPv4 addressing

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C03-21 | IP terminology | Bit, octet (8 bits), network address, broadcast address, host address | Host bits all 0 = network address; all 1 = broadcast address |
| C03-22 | IPv4 hierarchical structure and network addressing | 32-bit address split into a network portion and a host portion | Network part identifies the network; host part identifies the device |
| C03-23 | IPv4 Class A | First octet 1-126; default mask 255.0.0.0 (/8) | Few networks, very many hosts; 127 is reserved for loopback |
| C03-24 | IPv4 Class B | First octet 128-191; default mask 255.255.0.0 (/16) | Medium size |
| C03-25 | IPv4 Class C | First octet 192-223; default mask 255.255.255.0 (/24) | Many networks, 254 hosts each |
| C03-26 | IPv4 Class D | First octet 224-239; reserved for multicast | No network/host split; not assigned to single hosts |
| C03-27 | Private IP addresses (RFC 1918) | 10.0.0.0/8, 172.16.0.0/12 (172.16-172.31), 192.168.0.0/16 | Not routable on the internet; need NAT to reach it |
| C03-28 | IPv4 Layer-2 broadcast | Frame sent to MAC FF:FF:FF:FF:FF:FF | Reaches every device on the local segment; not forwarded by routers |
| C03-29 | IPv4 Layer-3 broadcast | Packet sent to an IP broadcast address (e.g., 255.255.255.255) | Addressed at the IP layer; routers do not forward the limited broadcast |
| C03-30 | IPv4 unicast | One sender to one receiver | One-to-one |
| C03-31 | IPv4 multicast | One sender to a group of interested receivers (224.0.0.0/4) | One-to-many, only to group members |

## D. Network Address Translation

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C03-32 | When to use NAT | Conserve public IPv4 addresses and connect private networks to the internet | Address translation, not a firewall |
| C03-33 | Types of NAT | Static (fixed one-to-one), dynamic (pool, one-to-one on demand), PAT/overload (many-to-one using ports) | Count of inside hosts per public address; PAT is the most common |
| C03-34 | NAT names | Inside local, inside global, outside local, outside global | Inside local = private address seen inside; inside global = public address seen outside |
| C03-35 | How NAT works | Router rewrites source address (and port for PAT), records it in a translation table, and reverses it for replies | Stateful translation table; no entry means return traffic is dropped |

## E. IPv6

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C03-36 | IPv6 addressing and expressions | 128-bit address written as eight 16-bit hexadecimal groups separated by colons | 128 bits vs IPv4's 32 |
| C03-37 | IPv6 shortened expression | Drop leading zeros in a group; replace one run of all-zero groups with :: | :: may appear only once per address |
| C03-38 | IPv6 address types | Unicast (global 2000::/3, link-local FE80::/10, unique local FC00::/7), multicast (FF00::/8), anycast | No broadcast in IPv6; multicast takes its role |
| C03-39 | IPv6 special addresses | ::1 loopback; :: unspecified; FE80::/10 link-local; FF02::1 all-nodes multicast | Loopback is ::1 (IPv4 equivalent is 127.0.0.1) |

---

## Chapter-specific question angles
- Port or protocol → identify the service (and whether it is secure or insecure)
- Scenario → choose the secure replacement (Telnet to SSH, HTTP to HTTPS, FTP/TFTP to SFTP)
- Address given → identify class, public vs private, or address type
- Worked NAT scenario → identify the NAT type or name the address (inside local vs inside global)
- IPv6 address → shorten it or identify its type
- Neighbor discrimination: FTP vs SFTP vs TFTP; TCP vs UDP; Layer-2 vs Layer-3 broadcast; APIPA vs private address; static NAT vs PAT
- "Which is NOT" on protocol ports, private ranges, or IPv6 address types
