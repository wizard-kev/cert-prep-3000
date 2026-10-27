# CCST Cybersecurity (100-160) | Chapter 9: Vulnerability

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 9 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 4.0 Vulnerability Assessment and Risk Management; incident documentation, chain of custody, and recovery items also fit 5.0 Incident Handling; reconnaissance and hardening items may touch 1.0 and 3.0)

**Usage:** IDs (`C09-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Vulnerability lifecycle

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-01 | Vulnerabilities | Weaknesses (software flaws, misconfigurations, weak processes) that can be exploited | The weakness itself; see C08-03 |
| C09-02 | Vulnerability identification | Discovering weaknesses through scans, testing, inventories, and threat intelligence | You cannot fix what you have not found |
| C09-03 | Vulnerability management | Ongoing cycle: identify, prioritize, remediate or mitigate, verify, report | A continuous process, not a one-time scan |
| C09-04 | Vulnerability mitigation | Reduce exposure when a full fix is not immediately possible (segmentation, ACLs, disabling the service) | Mitigation lowers risk; remediation (e.g., patching) removes the flaw; see C07-16, C08-12 |

## B. Active and passive reconnaissance

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-05 | Active vs passive reconnaissance | Passive = gather information without touching the target; active = interact with the target directly | Active can be detected and logged; passive generally cannot |
| C09-06 | Port scanning | Probes hosts for open ports and running services; used for both reconnaissance and testing | Active; finds open ports only, not known flaws; see C07-07, C07-09 |
| C09-07 | Vulnerability scanning | Automated checks of systems against known vulnerabilities (credentialed or non-credentialed) | Reports known weaknesses on those services; goes beyond a port scan |
| C09-08 | Packet sniffing / network traffic analysis | Capture and examine traffic to see protocols, cleartext credentials, and anomalies | Reveals what crosses the network; passive when only listening; see C07-06 |
| C09-09 | Brute-force attacks | Trying many credential combinations to test or break password strength | Active and noisy; lockouts counter it; see C01-29, C04-16 |
| C09-10 | OSINT | Information gathered from public sources (websites, social media, public records, job posts) | Passive; no direct contact with the target |
| C09-11 | DNS enumeration | Discovering a domain's hostnames, subdomains, and records | Mapping the DNS footprint; passive from public records, active when querying the target's DNS servers; see C07-02, C07-03 |
| C09-12 | Social engineering (reconnaissance) | Manipulating people to reveal information | Human-based and active; see C01-39 |

## C. Testing

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-13 | Testing | Systematic, authorized checks to find and confirm weaknesses | Authorized and scoped; confirms what scans suggest |
| C09-14 | Automation | Scheduled, scripted, tool-driven scans and checks | Fast, consistent, repeatable at scale; results still need human review and prioritization |

## D. Threat intelligence

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-15 | Threat intelligence | Information about threats, actors, tactics, and indicators used to anticipate and defend | External, actionable context; vulnerability findings are internal |
| C09-16 | Vulnerability databases | Public catalogs of known vulnerabilities (e.g., CVE identifiers, NVD, CVSS severity scores) | CVE = identifier; NVD = enriched database; CVSS = severity score |
| C09-17 | Limitations of vulnerability databases | Lag behind new discoveries, incomplete or inconsistent data, scores lack your environment's context | Do not list unknown (zero-day) flaws; a high score may matter little in a given environment |
| C09-18 | Assessment tools | Tools that assess systems (vulnerability scanners, port scanners, configuration auditors) | Automate discovery; output still needs analysis |

## E. Recommendations and hardening

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-19 | Recommendations | Specific, prioritized guidance that comes out of an assessment | The actionable output of assessment |
| C09-20 | Reduce surface area for attack | Disable unneeded services, ports, accounts, and software | Fewer exposed components means fewer vulnerabilities |
| C09-21 | Group Policy | Centrally manages and enforces settings on Windows computers and users | Central enforcement of configuration and security settings |
| C09-22 | GPOs | Group Policy Objects: bundles of settings linked to a site, domain, or OU | Applied in order local, site, domain, OU; later ones override earlier ones |
| C09-23 | Local group policy | Settings applied to a single computer | Scope is one machine |
| C09-24 | Domain group policy | Settings applied centrally to many computers and users through Active Directory | Scope is many machines; overrides local settings on conflict |
| C09-25 | SELinux mode | Mandatory access control on Linux with modes enforcing, permissive, and disabled (`getenforce`, `setenforce`) | Enforcing blocks and logs violations; permissive only logs |
| C09-26 | Samba | Linux/Unix implementation of SMB file and print sharing for Windows interoperability | Exposed SMB is attack surface: disable if unused, restrict shares, require authentication, disable SMBv1, keep patched |

## F. Reports and information sources

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-27 | Security reports | Summaries of assessment findings, vulnerabilities, and recommendations | Tailor to the audience (technical detail vs executive summary) |
| C09-28 | Cybersecurity news | Sources reporting emerging threats and vulnerabilities | Builds awareness; verify credibility |
| C09-29 | Subscription-based sources | Paid or subscribed threat-intelligence feeds and advisories | Curated and timely, often deeper than free sources; costs money |
| C09-30 | RSS feed | Automatic delivery of new items from chosen sites | Pulls updates to you without visiting each site |

## G. Documentation and incident handling records

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C09-31 | Documentation | Written record of processes, changes, and events | Makes actions repeatable and auditable |
| C09-32 | Updating documentation | Keep documents current as systems, processes, and lessons change | Outdated documentation misleads responders |
| C09-33 | Security incident documentation | Record of an incident: timeline, affected systems, actions taken, and who did what | Factual, time-stamped account |
| C09-34 | Chain of custody | Documented trail of who handled evidence, when, and how | A gap undermines the integrity and admissibility of evidence |
| C09-35 | Reporting incidents | Notifying the right parties (management, security team, legal, regulators, customers) per policy | Follow the defined reporting path; some timing is mandated by regulation; see C07-25 |
| C09-36 | Incident recovery | Restore affected systems to normal operation (clean backups, rebuild, validate) | Return to service after containment; see C07-31 |
| C09-37 | Reviewing the incident | Post-incident review to find root cause and improve controls | Happens after recovery; aims at improvement, not blame |
| C09-38 | Documentation best practices | Clear, accurate, timely, consistent, version-controlled, and securely stored | Document as you go; protect the documents because they can contain sensitive details |

---

## Chapter-specific question angles
- Scenario → classify an activity as active or passive reconnaissance
- Goal → choose the right technique (port scan vs vulnerability scan vs packet capture vs OSINT vs DNS enumeration)
- Scenario → explain a limitation of a vulnerability database or choose between CVE, NVD, and CVSS
- Mitigation vs remediation for a given situation
- Group Policy scenario → decide which setting wins (local, site, domain, OU) or whether scope is one machine or many
- SELinux mode → predict whether an action is blocked, logged, or both
- Hardening → choose the action that reduces attack surface (Samba, unused services)
- Scenario → identify the chain-of-custody gap, or put incident steps in order (document, report, recover, review)
- Neighbor discrimination: vulnerability scan vs port scan; local vs domain policy; enforcing vs permissive; recovery vs review
- "Which is NOT" on reconnaissance methods, information sources, or documentation practices
