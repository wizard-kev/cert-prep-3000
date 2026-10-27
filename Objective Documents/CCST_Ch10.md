# CCST Cybersecurity (100-160) | Chapter 10: Disaster Recovery

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 10 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (fit is uncertain: candidates are 1.0 Essential Security Principles for availability, 5.0 Incident Handling for recovery, and 4.0 for planning and testing)

**Usage:** IDs (`C10-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Data loss and backups

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C10-01 | Disaster prevention and recovery | Reduce the chance of disruptive events and restore operations when they happen | Prevention lowers likelihood; recovery restores service; see C02-01 (availability) |
| C10-02 | Data loss | Loss from hardware failure, deletion, corruption, ransomware, or disaster | Backups are the primary defense; see C01-20 |
| C10-03 | File-level backups | Back up selected files and folders | Fast and small, and restores individual files; cannot rebuild a whole system alone |
| C10-04 | Image-based backups | Capture the entire disk or system (OS, applications, settings, data) | Enables full-system (bare-metal) restore; larger |
| C10-05 | Critical applications | Identify applications essential to operations to set backup frequency and recovery order | Priority comes from business criticality |
| C10-06 | Network device backup/restore | Save device configurations (e.g., `copy running-config` to a remote server) and restore them after failure | Backs up configs, not user data; prefer secure transfer over TFTP; see C03-05 |
| C10-07 | Data restoration characteristics | How fast and how current a restore is: RTO (time to restore) and RPO (tolerable data loss) | RTO = how long; RPO = how much data, set by the age of the last backup |
| C10-08 | Backup media | Disk/NAS, tape, cloud, removable media, with trade-offs in cost, speed, capacity, and durability | Offline or offsite media survive ransomware and site loss |
| C10-09 | Backup methods | Full (everything), incremental (changes since the last backup of any type), differential (changes since the last full) | Incremental: fastest backup, slowest restore (full plus every incremental); differential: restore needs full plus the latest differential |
| C10-10 | Backup testing | Periodically restore data to verify integrity, completeness, and timing | An untested backup is unproven; see C07-24 |

## B. Account recovery

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C10-11 | Online account recovery | Reset through email, phone, recovery codes, or MFA | The recovery channel is itself an attack path; protect it |
| C10-12 | Local account recovery | Reset by another local administrator or by recovery media/tools | Depends on a second admin account or physical access; no central reset |
| C10-13 | Domain account recovery | Reset or unlock by a domain administrator or help desk in the directory | Managed centrally; self-service reset is possible |

## C. Facilities and infrastructure support

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C10-14 | Battery backup | Short-term power during an outage | Runtime in minutes, not hours |
| C10-15 | UPS | Battery-backed power that also conditions input power | Bridges to a graceful shutdown or generator start; not long-term power |
| C10-16 | Standby UPS | Passes utility power and switches to battery on failure | Brief switchover gap; lowest cost and least protection |
| C10-17 | Line-interactive UPS | Regulates voltage sags and surges without using the battery, then switches on outage | Handles voltage fluctuation; mid-range |
| C10-18 | Online UPS | Double conversion: equipment always runs from the inverter | No transfer time; best protection and highest cost |
| C10-19 | Power generators | Long-duration backup power (diesel or natural gas) | Takes time to start, so a UPS bridges the gap; needs fuel and testing |
| C10-20 | Surge protection | Diverts excess voltage spikes away from equipment | Protects against spikes, not outages; not a UPS |
| C10-21 | PDU | Distributes power to rack equipment (metered and switched versions add monitoring and remote outlet control) | Distribution, not backup; gains backup only when fed by a UPS |
| C10-22 | HVAC | Controls temperature, airflow, and humidity | Overheating causes failures; cooling is a continuity control |
| C10-23 | ASHRAE standards | Recommended temperature and humidity ranges for computing environments (about 18-27 C) | Too dry raises static discharge risk; too humid causes condensation and corrosion |
| C10-24 | Fire suppression | Extinguish fires while limiting damage to people and equipment | Match the system to the space: water-based vs clean agent |
| C10-25 | Wet pipe systems | Pipes always hold water; heat opens a sprinkler head | Simplest and fastest; accidental discharge or leaks can damage electronics |
| C10-26 | Dry pipe systems | Pipes hold pressurized gas; water enters after a head opens | Used where pipes could freeze; slower water delivery |
| C10-27 | Preaction systems | Pipes dry; water enters only after detection, and a head must then open | Two-step trigger lowers accidental-discharge risk; common in data centers |
| C10-28 | Deluge systems | Open heads discharge water from all heads on detection | Massive water flow for high-hazard areas |
| C10-29 | Clean agent systems | Gaseous suppression that leaves no residue | No water damage; suited to equipment rooms |
| C10-30 | Halon | Effective gaseous agent that depletes ozone | Production banned (EPA); only legacy systems remain |
| C10-31 | Argon | Inert gas that displaces oxygen | Inert gas; safe for equipment; works by oxygen reduction |
| C10-32 | NAF-S-III | Chemical clean agent developed as a halon replacement | A replacement for halon |
| C10-33 | FM-200 | Chemical clean agent (HFC-227ea) with fast discharge | Widely used in data centers; leaves no residue |

## D. Redundancy and high availability

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C10-34 | Switch clustering | Multiple switches operate as one logical switch | A single switch failure does not cut connectivity |
| C10-35 | Router redundancy | Redundant routers and multiple paths with first-hop redundancy | The default gateway stays available |
| C10-36 | Firewall redundancy | High-availability pairs (active/standby or active/active) that share session state | State sharing lets sessions survive failover |
| C10-37 | Server redundancy | Clustering, load balancing, redundant power supplies, and RAID | Removes single points of failure |
| C10-38 | Disaster recovery sites | Alternate location to resume operations | Trade-off between cost and recovery time |
| C10-39 | Cold site | Space with power and connectivity but no equipment or data | Cheapest and slowest (days to weeks) |
| C10-40 | Warm site | Partly equipped, with data restored from backups | Middle ground in cost and time |
| C10-41 | Hot site | Fully equipped with near-real-time data replication | Fastest and most expensive |
| C10-42 | Cloud site | Recovery environment in a cloud provider, scaled on demand | Lower upfront cost and elastic; depends on connectivity, provider, and testing |
| C10-43 | Active/active vs active/passive | Active/active: all nodes serve traffic; active/passive: a standby takes over on failure | Active/active shares load but loses capacity on failure; active/passive leaves resources idle |
| C10-44 | Multiple ISPs and diverse paths | More than one provider and physically separate routes | Diversity must be physical; two contracts in one conduit still share a failure point |

## E. Testing and plans

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C10-45 | Tabletop exercises | Team talks through a disaster scenario without touching systems | Discussion only; tests roles and plans |
| C10-46 | Validation tests | Hands-on tests that confirm recovery procedures and systems work | Actually exercises systems, unlike a tabletop |
| C10-47 | Disaster recovery plan | Documented procedures to restore IT systems and data after a disruption | IT-focused restoration |
| C10-48 | Business continuity plan | Keeps critical business operations running during and after a disruption | Broader than IT; the DRP is a part of it |

---

## Chapter-specific question angles
- Scenario → choose full, incremental, or differential, and state what is needed to restore
- Given RTO, RPO, and budget → choose the DR site type (cold, warm, hot, cloud)
- Scenario → choose the UPS type, or decide whether a UPS, surge protector, or generator is needed
- Scenario → choose the fire suppression system for a data center and justify it
- Cause and effect: temperature or humidity out of range → consequence (ASHRAE)
- Active/active vs active/passive for a described outage
- Scenario → account recovery path for an online, local, or domain account
- Tabletop vs validation test; DRP vs BCP
- Neighbor discrimination: wet pipe vs dry pipe vs preaction vs deluge; file-level vs image-based backup; RTO vs RPO
- "Which is NOT" on power protection, fire suppression agents, or backup types
