# CCST Cybersecurity (100-160) | Chapter 1: Security Concepts

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 1 (user-supplied list, plus user-approved additions)
**File version:** v2 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 1.0 Essential Security Principles; hardening and L2 items may also touch 2.0)

**Usage:** IDs (`C01-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions.

---

## A. Denial of Service family (availability)

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C01-01 | DoS / DDoS | Exhaust a resource so legitimate users can't be served | DDoS = many distributed sources; DoS = one source |
| C01-02 | Botnet | Network of compromised devices under attacker control | The *army*; the means, not the attack |
| C01-03 | Command and Control (C2) | Channel/infrastructure used to issue commands to compromised devices | The *orders*; botnet = devices, C2 = control path |
| C01-04 | Traffic spike | Sudden surge in volume | Symptom only; cause may be malicious or legitimate |
| C01-05 | Coordinated attack | Multiple sources/actors acting together | Overlaps with DDoS; emphasis is synchronization |
| C01-06 | Friendly / unintentional DoS | Outage with no malicious intent (viral demand, misconfiguration, runaway process) | No attacker; intent is the differentiator |
| C01-07 | Physical attack | Damaging, cutting, or powering off infrastructure | Hits availability with no network traffic |
| C01-08 | Permanent DoS | Corrupts device firmware so it is unusable | Needs reflash/replacement; reboot won't fix it |
| C01-09 | Smurf | ICMP echo to a broadcast address with the victim's spoofed source IP | Victim flooded by replies from many hosts |
| C01-10 | SYN flood | Floods a server with TCP SYNs, never completing the handshake | Fills the half-open connection table |
| C01-11 | Reflective / amplified attacks | Spoofed requests to third-party servers; small request, large response to victim | Reflective = third party bounces it; amplified = response larger than request |

## B. Interception, spoofing, and Layer 2 / network attacks

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C01-12 | On-path attack (formerly MitM) | Attacker sits between two parties to read or alter traffic | Breaks confidentiality/integrity of a live session |
| C01-13 | DNS poisoning | False records inserted into a resolver/cache | User enters the right name, reaches the wrong IP |
| C01-14 | VLAN hopping | Reaching a VLAN you aren't assigned to (switch spoofing or double tagging) | Double tagging exploits the native VLAN |
| C01-15 | ARP spoofing | Forged ARP replies map attacker's MAC to another host's IP | Local subnet only; commonly enables on-path |
| C01-16 | Rogue DHCP | Unauthorized DHCP server hands out bad gateway/DNS | Countered by DHCP snooping (trusted vs untrusted ports) |
| C01-17 | IoT vulnerabilities | Default credentials, unpatched firmware, weak/no encryption | Frequent source of botnet recruits |
| C01-18 | Rogue AP | Unauthorized access point plugged into the wired network | Sits *inside* your network; a backdoor |
| C01-19 | Evil twin | Attacker AP imitating a legitimate SSID | Targets *users*; rogue AP targets the *network* |

## C. Malware and credential attacks

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C01-20 | Ransomware | Encrypts data and demands payment for the key | Extortion for access; data is held, not necessarily stolen |
| C01-21 | Trojan | Malicious code disguised as legitimate software | User must run it; does not self-replicate |
| C01-22 | Worm | Self-replicating malware that spreads over networks | Spreads with no user action and no host file |
| C01-23 | Virus | Malicious code that attaches to a legitimate file/program | Needs a host and user action to spread |
| C01-24 | Spyware | Secretly collects user activity and data | Goal is covert information gathering |
| C01-25 | Keylogger | Records keystrokes to capture credentials and input | Specific capture method; often delivered by spyware or a trojan |
| C01-26 | Rootkit | Hides deep in the OS/kernel/firmware to keep privileged, stealthy access | Defined by concealment; hides itself and other malware |
| C01-27 | Adware | Delivers unwanted ads, often bundled with free software | Nuisance/tracking focus; may degrade performance |
| C01-28 | Malvertising | Malicious ads on legitimate sites that redirect or deliver malware | Attack rides on ad networks; site itself isn't compromised |
| C01-29 | Brute force | Tries every possible combination | Exhaustive; slow; defeated by lockouts and length |
| C01-30 | Dictionary attack | Tries words from a precompiled list | Guesses *likely* passwords, not all of them |
| C01-31 | Advanced Persistent Threat (APT) | Stealthy, long-term, targeted intrusion, often well-resourced | Defined by persistence and dwell time |

## D. Hardening and defense in depth

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C01-32 | Change default credentials | Replace vendor logins before deployment | Counters default-login exploitation (IoT) |
| C01-33 | Avoid common passwords | Block easily guessed passwords | Counters dictionary attacks |
| C01-34 | DHCP snooping | Switch feature that accepts DHCP offers only from trusted ports | Counters rogue DHCP |
| C01-35 | Change native VLAN | Move native VLAN off the default | Counters double-tagging VLAN hopping |
| C01-36 | Patching and updating | Fix known software vulnerabilities | Software; contrast with firmware |
| C01-37 | Upgrading firmware | Update device-level code | Embedded in hardware; contrast with OS/app patching |
| C01-38 | Defense in depth | Layered, overlapping controls | No single control is relied on |

## E. Social, insider, and physical-access threats

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C01-39 | Social engineering | Manipulating people rather than systems | Umbrella category for the phishing and physical-access items below |
| C01-40 | Insider threats | Harm from someone with legitimate access (malicious or accidental) | Already inside the perimeter; intent can be either |
| C01-41 | Phishing | Fraudulent messages (typically email) to steal data or credentials | Broad, untargeted |
| C01-42 | Vishing | Phishing by voice/phone | Medium = voice |
| C01-43 | Smishing | Phishing by SMS/text | Medium = text message |
| C01-44 | Spear phishing | Phishing tailored to a specific person or group | Targeted; uses personal detail |
| C01-45 | Whaling | Spear phishing aimed at executives/high-value targets | Target seniority is the differentiator |
| C01-46 | Tailgating | Unauthorized person follows an authorized person through a secured entry *without* their knowledge or consent | Unknowing victim |
| C01-47 | Piggybacking | Unauthorized person enters *with* an authorized person's knowledge or consent | Knowing/willing insider, e.g. holding the door |
| C01-48 | Shoulder surfing | Observing screens/keypads to capture information | Visual observation; no technical exploit |

---

## Question-angle bank (anti-repetition seeds)
Rotate framings per objective so the same objective is never tested the same way twice in a row:
- Symptom → identify the attack (log excerpt, user complaint, traffic description)
- Attack → select the correct mitigation
- Mitigation → identify the threat it addresses
- Neighbor discrimination (A vs B; pick the fact that separates them)
- Scenario with a distractor matching a *different* attack
- "Which is NOT" / exception-style
- Root cause vs symptom
- Cause-and-effect ordering
