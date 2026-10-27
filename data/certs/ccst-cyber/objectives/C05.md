# CCST Cybersecurity (100-160) | Chapter 5: Secure Access Technology

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 5 (user-supplied list, plus user-requested additions in Section E)
**File version:** v2 | **Domain tags:** provisional until checked against Cisco's blueprint (ACLs, firewalls, VPNs, IPsec, GRE fit 2.0 Basic Network Security Concepts; encryption, hashing, PKI also fit 1.0 Essential Security Principles)

**Usage:** IDs (`C05-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See C01-xx / C02-xx / C03-xx / C04-xx" marks a cross-chapter link usable for mixed questions.

---

## A. ACLs and firewalls

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C05-01 | ACLs | Ordered permit/deny statements that filter traffic on a router interface (inbound or outbound) | Processed top-down, first match wins; implicit deny at the end |
| C05-02 | Standard ACLs | Filter on source IP address only (numbered 1-99, 1300-1999) | Source only, so place close to the destination |
| C05-03 | Wildcard masking | Inverse mask: 0 = bit must match, 1 = bit is ignored (0.0.0.255 matches a /24) | Opposite of a subnet mask; `host` = 0.0.0.0, `any` = 255.255.255.255 |
| C05-04 | Extended ACLs | Filter on source, destination, protocol, and ports (numbered 100-199, 2000-2699) | More granular, so place close to the source |
| C05-05 | Firewalls | Enforce policy between networks; add session awareness beyond ACL filtering | ACLs are stateless filters; stateful firewalls track sessions; see C02-36 to C02-40 |

## B. Encryption and hashing

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C05-06 | Encryption | Converts plaintext to ciphertext with an algorithm and a key | Provides confidentiality; not integrity or authentication on its own; see C02-27 |
| C05-07 | Symmetric key encryption | The same key encrypts and decrypts | Fast, suited to bulk data; key distribution is the challenge |
| C05-08 | DES | 56-bit key, 64-bit blocks | Obsolete and insecure |
| C05-09 | 3DES | Applies DES three times | Deprecated stopgap; slow; replaced by AES |
| C05-10 | AES | 128-, 192-, or 256-bit keys | Current standard symmetric cipher |
| C05-11 | Hashes | One-way function producing a fixed-length digest | Verifies integrity; not reversible, so not encryption |
| C05-12 | MD5 | 128-bit digest | Broken (collisions); avoid for security use |
| C05-13 | SHA | Secure Hash Algorithm family (SHA-1, SHA-2, SHA-3) | SHA-1 is deprecated; SHA-256 or longer is preferred |

## C. VPNs, IPsec, and GRE

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C05-14 | VPN benefits and use cases | Encrypted tunnel across an untrusted network such as the internet | Remote access (user to site) vs site-to-site; cheaper than leased lines |
| C05-15 | Enterprise VPNs | Built and managed by the organization (IPsec, SSL VPN) over the internet | Customer-controlled security |
| C05-16 | Provider-managed VPNs | Service provider operates the VPN (e.g., MPLS-based) | Provider isolates customer traffic; not necessarily encrypted |
| C05-17 | IPsec | Suite securing IP traffic: confidentiality, integrity, authentication, anti-replay | A framework (IKE plus AH/ESP), not a single protocol |
| C05-18 | Cisco IOS IPsec | Configured with an IKE policy, a transform set, and a crypto map or profile applied to an interface | IKE phase 1 builds the secure management channel; phase 2 builds the data SAs |
| C05-19 | IPsec security protocols | AH (protocol 51): integrity and authentication; ESP (protocol 50): encryption plus integrity and authentication | AH does not encrypt; ESP is the one that does |
| C05-20 | IPsec encryption | ESP uses symmetric ciphers (AES preferred); keys negotiated via IKE with Diffie-Hellman; tunnel mode vs transport mode | Tunnel = whole original packet encapsulated (site-to-site); transport = payload only |
| C05-21 | GRE tunnels | Encapsulation (IP protocol 47) that can carry many protocols, including multicast and routing protocols | Flexible but provides no encryption |
| C05-22 | GRE over IPsec | GRE tunnel protected by IPsec | GRE adds multi-protocol/multicast support; IPsec adds encryption |
| C05-23 | Cisco DMVPN | Hub-and-spoke VPN with dynamic spoke-to-spoke tunnels (mGRE, NHRP, IPsec) | Scales without configuring a full mesh |
| C05-24 | Cisco IPsec VTI | IPsec tunnel as a routable virtual interface | Route-based, no GRE header; contrast with policy-based crypto maps |

## D. Public key infrastructure

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C05-25 | Public key infrastructure (PKI) | Framework of CAs, certificates, policies, and processes that bind public keys to identities | The whole trust system, not one component |
| C05-26 | Certificate authorities | Trusted entities that issue, sign, and revoke certificates | The trust anchor; signs with its own private key |
| C05-27 | Certificate template | Predefined settings (key usage, validity, key size, subject fields) a CA applies when issuing certificates | The blueprint for issuance, not a certificate itself |
| C05-28 | Certificates | Signed digital document binding a public key to an identity (X.509) | Holds the public key, never the private key; validated by CA signature, dates, and revocation status; see C03-08 |

## E. ACL configuration on Cisco IOS CLI (user-requested additions)

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C05-29 | Standard ACL commands | Global config: `access-list 10 permit 192.168.1.0 0.0.0.255`, `access-list 10 deny host 10.1.1.5` | Number, action, source (plus wildcard); no protocol or ports |
| C05-30 | Extended ACL commands | `access-list 110 permit tcp 192.168.1.0 0.0.0.255 host 10.1.1.10 eq 80` | Order is action, protocol, source, destination, then port |
| C05-31 | Named ACLs | `ip access-list extended WEB-IN`, then entries such as `permit tcp any any eq 443` in ACL config mode | `standard` or `extended` keyword is required; entries omit the `access-list` keyword |
| C05-32 | Applying an ACL to an interface | `interface g0/0` then `ip access-group 110 in` (or `out`) | An unapplied ACL filters nothing; direction is relative to the router; one ACL per protocol, interface, and direction |
| C05-33 | Applying an ACL to VTY lines | `line vty 0 4` then `access-class 10 in` | `access-class` limits management sessions to the device; `ip access-group` filters traffic through an interface; see C04-01 |
| C05-34 | Entry order and sequence numbers | New numbered entries append to the end; sequence numbers (10, 20, ...) allow inserting or deleting entries in named ACLs | A broad entry above a specific one shadows it; implicit deny follows the last entry, so an explicit permit may be needed |
| C05-35 | Port and protocol keywords | Protocols `tcp`, `udp`, `icmp`, `ip`; operators `eq`, `neq`, `gt`, `lt`, `range`; names or numbers (`www` or 80, 22, 23) | Ports require `tcp` or `udp`; `ip` matches all traffic and cannot take ports |
| C05-36 | Verifying ACLs | `show access-lists` (entries, sequence numbers, match counts), `show ip interface g0/0` (applied ACL and direction), `show running-config` | `show access-lists` = what the ACL says and its hits; `show ip interface` = where it is applied |
| C05-37 | Removing and documenting ACLs | `remark` documents an entry; `no ip access-group 110 in` removes the application only; `no access-list 110` deletes the whole ACL | Removing the application vs deleting the ACL itself |

---

## Chapter-specific question angles
- Given a requirement → choose standard or extended ACL, and where to place it
- Subnet or address range → write the wildcard mask; or given an ACL, decide whether a packet is permitted (top-down, implicit deny)
- CLI: complete the missing command or keyword for a stated requirement (e.g., apply inbound on an interface, restrict VTY access)
- CLI: find the error in a configuration fragment (subnet mask used instead of wildcard, specific entry shadowed by a broad one, wrong direction, ACL never applied, ports used with `ip`, wrong config mode)
- CLI: put the commands in the correct order or name the config mode each belongs in
- CLI: read `show access-lists` or `show ip interface` output and state what it reveals
- Scenario → choose the cipher or hash and reject deprecated ones (DES, 3DES, MD5, SHA-1)
- Classify a mechanism: encryption vs hashing vs digital certificate
- Scenario → choose AH vs ESP, or tunnel vs transport mode
- Scenario → choose GRE vs IPsec vs GRE over IPsec, or DMVPN vs VTI
- Neighbor discrimination: enterprise vs provider-managed VPN; certificate vs template vs CA; standard vs extended ACL; `access-group` vs `access-class`
- "Which is NOT" on symmetric ciphers, hash algorithms, or IPsec components
