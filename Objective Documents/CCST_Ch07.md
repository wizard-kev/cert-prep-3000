# CCST Cybersecurity (100-160) | Chapter 7: Endpoint Security

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 7 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 3.0 Endpoint Security Concepts; tools may also touch 2.0 and 4.0; backups and recovery may touch 5.0)

**Usage:** IDs (`C07-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. CLI tools

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-01 | netstat | Shows active connections, listening ports, routing table, and interface statistics on the local host (`netstat -an`) | Local view of what is connected or listening; useful for spotting unexpected connections |
| C07-02 | nslookup | Queries DNS to resolve names to IPs and back (`nslookup example.com`) | Basic DNS troubleshooting on Windows and Linux; see C03-10 |
| C07-03 | dig | Detailed DNS query tool (`dig example.com MX`) | More detailed than nslookup (record sections, TTL, query time); Linux/macOS |
| C07-04 | ping | ICMP echo test of reachability and round-trip time | A failed ping does not prove the host is down; ICMP may be blocked; see C03-19 |
| C07-05 | tracert | Shows each hop along the path to a destination (`tracert` on Windows; `traceroute` on Linux/macOS) | Locates *where* along the path connectivity fails |
| C07-06 | tcpdump | Command-line packet capture and analysis (`tcpdump -i eth0 port 53`) | Captures actual packets; netstat only lists connections |
| C07-07 | nmap | Scans hosts for live devices, open ports, services, and OS details | Probes *other* hosts; netstat reports the local host |
| C07-08 | gpresult | Shows Group Policy settings applied to a user or computer (`gpresult /r`) | Windows only; confirms which policies actually applied |

## B. Software tools

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-09 | Port scanner | Probes a host to find open, closed, or filtered ports | Answers "which ports on this host?" |
| C07-10 | iPerf | Measures network throughput between two endpoints (client and server, TCP or UDP) | Performance testing, not security scanning |
| C07-11 | IP scanner | Discovers active devices across an address range (ping sweep) | Answers "which hosts are on this network?"; finds rogue devices; see C01-18 |

## C. Inventory, assets, and remediation

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-12 | Hardware inventory | Record of physical devices (type, serial, owner, location, status) | You cannot protect devices you do not know exist |
| C07-13 | Asset management systems | Software that tracks assets from purchase through disposal | The system of record; a tag is only the physical identifier |
| C07-14 | Asset tags | Physical or barcode/RFID label with a unique ID on a device | Ties the physical device to its inventory record |
| C07-15 | Software inventory | Record of installed software, versions, and licenses | Versions reveal vulnerable software; also flags unauthorized or unlicensed programs |
| C07-16 | Remediation | Fixing or mitigating identified vulnerabilities and non-compliance (patch, reconfigure, remove, isolate) | Acts on findings; discovery alone fixes nothing |
| C07-17 | Remediation considerations | Weigh risk and priority, business impact, testing, maintenance windows, dependencies, and a rollback plan | Test before wide deployment; prioritize by risk |

## D. Destruction and disposal

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-18 | Destruction and disposal | Retire devices and media so data cannot be recovered, following policy and documenting it | Deleting files is not sanitizing |
| C07-19 | Low-level format vs standard format | Standard format rebuilds file system structures; low-level format overwrites every sector | Standard format leaves data recoverable |
| C07-20 | Hard drive sanitization | Making data unrecoverable; method depends on data sensitivity and whether the drive will be reused | Reuse allows overwrite or wipe; highest sensitivity points to destruction |
| C07-21 | Overwrite | Writing patterns over all addressable areas of the media, one or more passes | Allows reuse; less reliable on SSDs and failed sectors |
| C07-22 | Drive wipe | Tool-driven erase of the whole drive (wipe utilities, firmware secure erase, cryptographic erase), often with verification | Automated and reportable; supports reuse; wipe tools typically apply overwrite |
| C07-23 | Physical destruction | Shredding, crushing, incineration, or degaussing (magnetic media) | Most certain; drive is unusable; degaussing does not work on SSDs |

## E. Backups, compliance, and device ownership

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-24 | Data backups | Copies of data for recovery after loss, failure, or ransomware | An untested backup is unproven; offline or offsite copies resist ransomware; see C01-20 |
| C07-25 | Regulatory compliance | Meeting external legal and industry requirements for handling data (e.g., HIPAA, PCI DSS, GDPR) | Externally imposed, unlike internal policy |
| C07-26 | BYOD vs organization-owned | BYOD = employee-owned device; organization-owned = full organizational control | Ownership drives how much control and privacy there is; see C04-22 |
| C07-27 | MDM | Central platform to enroll, configure, and enforce policy on mobile devices (remote lock/wipe) | The platform; the next three items are things it manages |
| C07-28 | Configuration management | Maintain consistent, documented, approved configurations (baselines) under change control | Baseline plus change control; detects configuration drift |
| C07-29 | App distribution | Control which apps are installed and from where (managed app store, allow/block lists) | Governs software sources on managed devices |
| C07-30 | Data encryption | Protect data on the device (e.g., full-disk encryption) | A lost or stolen device does not expose readable data; see C05-06 |

## F. Endpoint protection and recovery

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-31 | Endpoint recovery | Restore an endpoint to a known-good state (restore from backup, reimage, rebuild) | Recovery after a problem; protection tries to prevent it |
| C07-32 | Endpoint protection | Controls on the device: antimalware, host-based firewall, host intrusion detection, EDR | Preventive and detective controls on the endpoint itself |
| C07-33 | Cloud-based protection | Endpoint security delivered or analyzed through the cloud (cloud signatures, threat intelligence, central console) | Fast updates and off-network coverage; needs connectivity |
| C07-34 | Reviewing scan logs | Examine antimalware and vulnerability scan results for detections, failures, and patterns | A clean log does not prove safety; check that scans ran and definitions were current |

## G. Malware remediation (ordered process)

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C07-35 | Malware remediation process | Seven steps in order: identify and verify symptoms; quarantine; disable System Restore; remediate; schedule scans and run updates; re-enable System Restore and create restore points; educate users | Sequence matters; ordering questions test it |
| C07-36 | Identify and verify malware symptoms | Gather symptoms (slowness, pop-ups, redirects, disabled antivirus, unknown processes) and confirm it is malware | First step; confirm before acting |
| C07-37 | Quarantine infected systems | Isolate from the network (disconnect or isolate VLAN) | Stops spread before cleaning; see C01-22 |
| C07-38 | Disable System Restore in Windows | Turn off System Restore so malware in old restore points is not preserved | Done before cleaning; restore points can hold malware |
| C07-39 | Remediate infected systems | Update antimalware, scan, and remove, using safe mode or rescue media when needed | Use current definitions; rescue media helps with stealthy malware such as rootkits; see C01-26 |
| C07-40 | Schedule scans and run updates | Patch the OS and applications, update signatures, and schedule recurring scans | Closes the hole that let the malware in |
| C07-41 | Enable System Restore and create restore points | Turn System Restore back on and create a fresh restore point | Only after the system is verified clean |
| C07-42 | Educate end users | Train users on phishing, safe downloads, and reporting | Final step; prevents recurrence; see C01-39 |

---

## Chapter-specific question angles
- Scenario → choose the right tool (netstat vs nmap, nslookup vs dig, ping vs tracert, tcpdump vs port scanner)
- Command output or syntax → identify the tool, or the Windows vs Linux equivalent (`tracert` vs `traceroute`)
- Goal → choose the disposal method given reuse vs disposal, sensitivity, and drive type (HDD vs SSD)
- Standard format vs low-level format; overwrite vs drive wipe vs physical destruction
- Put the seven malware remediation steps in order, or identify which step comes next or was skipped
- Scenario → choose the control (MDM, configuration management, app distribution, encryption) for a BYOD problem
- Protection vs recovery vs remediation; asset tag vs asset management system; hardware vs software inventory
- "Which is NOT" on CLI tool functions or sanitization methods
