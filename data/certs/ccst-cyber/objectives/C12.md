# CCST Cybersecurity (100-160) | Chapter 12: Digital Forensics

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 12 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 5.0 Incident Handling)

**Usage:** IDs (`C12-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Investigation frameworks and models

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C12-01 | Forensic incident response | Using forensic techniques during incident response to learn what happened, how far it spread, and why, while preserving evidence | Investigation with evidence integrity, not only restoring service; see C09-33 |
| C12-02 | Attack attribution | Identifying who is behind an attack from evidence such as TTPs, infrastructure, malware, and timing | Identifies the *actor*, not just the technique; uncertain because evidence can be spoofed or planted |
| C12-03 | Lockheed Martin Cyber Kill Chain | Seven stages: reconnaissance, weaponization, delivery, exploitation, installation, command and control, actions on objectives | Ordered, linear model of an intrusion; stopping any stage disrupts the attack; see C01-03, C09-05 |
| C12-04 | MITRE ATT&CK matrix | Knowledge base of real-world adversary tactics and techniques arranged as a matrix | Not linear; tactics (why) as columns and techniques (how) beneath them; used to map detection coverage |
| C12-05 | Diamond Model | Describes an intrusion event through four features: adversary, capability, infrastructure, victim | Four connected vertices for a single event; analysts pivot between them |
| C12-06 | TTPs | Tactics (goals), techniques (methods), and procedures (specific implementations) that describe attacker behavior | Behavior-based and harder for attackers to change than IoCs such as IPs or hashes; see C11-13 |

## B. Evidence

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C12-07 | Artifacts and sources of evidence | Logs, memory, disk images, network captures, registry data, browser history, email, device and cloud data, and metadata | Collect volatile data first (order of volatility: memory and running state before disk) |
| C12-08 | Evidence handling | Collecting, labeling, storing, transferring, and controlling access to evidence, with documentation at every step | The umbrella for preservation and chain of custody |
| C12-09 | Preserving digital evidence | Make bit-for-bit forensic copies, work from the copy, use write blockers, and verify integrity with hashes | Never examine the original; matching hashes show the copy is unchanged |
| C12-10 | Chain of custody | Documented record of who handled evidence, when, where, and why | A gap undermines integrity and admissibility; same concept as C09-34 |

---

## Chapter-specific question angles
- Put the Cyber Kill Chain stages in order, or map an observed activity to its stage
- Scenario → choose the model that fits (Kill Chain for stages, ATT&CK for techniques, Diamond Model for relationships in one event)
- Name the Diamond Model feature (adversary, capability, infrastructure, victim) from a description
- Classify an indicator as a TTP or an IoC
- Order the evidence to collect first (order of volatility)
- Scenario → identify what should have been done to preserve evidence (forensic copy, write blocker, hash, documentation)
- Scenario → identify the chain-of-custody gap
- Why attribution is uncertain: false flags, shared tools, spoofed infrastructure
- Neighbor discrimination: Kill Chain vs ATT&CK; tactic vs technique vs procedure; evidence handling vs chain of custody
- "Which is NOT" a Kill Chain stage or Diamond Model feature
