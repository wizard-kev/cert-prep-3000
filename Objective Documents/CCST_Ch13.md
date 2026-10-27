# CCST Cybersecurity (100-160) | Chapter 13: Incident Response

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 13 (user-supplied list; repeated items consolidated)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 5.0 Incident Handling; incident types and prevention may also touch 1.0 and 4.0)

**Usage:** IDs (`C13-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Incident handling and incident types

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-01 | Incident handling | The overall process of preparing for, detecting, responding to, and learning from incidents | The umbrella; runs as a lifecycle, not a one-time event |
| C13-02 | Security incidents | Events that violate or threaten security policy or harm confidentiality, integrity, or availability | An *event* is any observable occurrence; an *incident* is an event with an adverse effect |
| C13-03 | Ransomware incident | Data encrypted for payment; response relies on isolation, backups, and a pre-set payment policy | Contain first, restore from clean backups; see C01-20, C07-24 |
| C13-04 | Social engineering incident | People manipulated into giving access or information | Response includes credential resets and user education; see C01-39 |
| C13-05 | Phishing incident | Fraudulent messages used to steal credentials or deliver malware | Report, block the sender and URLs, reset exposed credentials; see C01-41 |
| C13-06 | DDoS incident | Flood of traffic from many sources exhausts a resource | Mitigation often needs upstream help from the ISP; see C01-01, C13-35 |
| C13-07 | Supply chain attacks | Compromise delivered through a trusted vendor, software update, or component | Arrives through a trusted third party, so it is hard to detect |
| C13-08 | Insider threats | Harm from someone with legitimate access | Response includes access revocation and monitoring; see C01-40 |

## B. Incident response planning

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-09 | Incident response planning | Preparing plans, teams, tools, and policies before incidents occur | Done in advance, not during the incident |
| C13-10 | Incident response plan | Documented roadmap of roles, procedures, communication, and escalation | Plan = procedures; policy = authority and requirements (C13-29) |
| C13-11 | CSIRT team | Computer Security Incident Response Team: group that handles incidents | Cross-functional; includes non-technical roles (legal, HR, communications, management) |
| C13-12 | Specifically defined responsibilities | Each person's role is assigned in advance (who decides, who communicates, who acts) | Clear roles prevent gaps and duplicated effort |
| C13-13 | Business continuity plan (in the IR plan) | Keeps critical business functions running during an incident | Business-wide continuity; see C10-48 |
| C13-14 | Communications plan | Defines who is informed, how, when, and by whom, internally and externally | Uses a designated spokesperson; backup channels matter if normal ones are compromised |
| C13-15 | Specifically defined documentation standards | Consistent templates and formats for recording incident details | Consistency makes timelines and evidence reliable; see C09-38 |
| C13-16 | Incident response frameworks | Structured guidance for organizing incident response | Frameworks give a common set of phases and terms |
| C13-17 | SANS | Six steps: preparation, identification, containment, eradication, recovery, lessons learned | SANS separates containment, eradication, and recovery |
| C13-18 | NIST | US standards body whose publications guide incident response | NIST provides the four-phase lifecycle commonly tested |
| C13-19 | NIST SP 800-61 | Computer Security Incident Handling Guide; Revision 2 lifecycle: preparation; detection and analysis; containment, eradication, and recovery; post-incident activity | NIST combines containment, eradication, and recovery into one phase; Revision 3 (April 2025) supersedes Revision 2 and aligns to CSF 2.0 functions |
| C13-20 | CISA | US Cybersecurity and Infrastructure Security Agency: provides guidance, alerts, and a place to report incidents | Government agency and reporting point, not a lifecycle model |
| C13-21 | Incident preparation | Policies, trained team, tools, baselines, and communication ready before an incident | First phase; also covers prevention planning |
| C13-22 | Risk assessments (preparation) | Identify likely threats, vulnerabilities, and valuable assets to focus preparation | Drives priorities; see C08-02 |
| C13-23 | Detection and analysis | Detect, validate, scope, and prioritize a suspected incident | Follows preparation; determines whether and how bad |
| C13-24 | Containment | Limit spread and damage (isolate hosts, block addresses, disable accounts) | Stops the damage first; precedes eradication |
| C13-25 | Eradication | Remove the cause (malware, compromised accounts, exploited weakness) | Removes root cause; follows containment |
| C13-26 | Recovery | Restore systems to normal operation, verify, and monitor for recurrence | Returns to service after eradication |
| C13-27 | Post-incident review | Meeting after resolution to examine what happened and how it was handled | Follows recovery; aimed at improvement, not blame |
| C13-28 | Lessons learned | Documented findings that feed back into plans, controls, and training | The output that loops back into preparation |

## C. Incident response policy and outside parties

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-29 | Creating an incident response policy | Formal policy setting authority, scope, definitions, roles, severity levels, and reporting rules | Policy = high-level authority and requirements; plan = procedures |
| C13-30 | Document how information is shared with outside parties | Policy defines what may be shared, with whom, by whom, and through which channels | Decided in advance and routed through designated people (often with legal review) |
| C13-31 | Outside parties | External groups involved in an incident (law enforcement, regulators, ISPs, vendors, customers, media) | Contact only through the defined channels |
| C13-32 | Interfacing with law enforcement | Decide in advance when and how to involve law enforcement, with legal counsel | Evidence handling and chain of custody affect admissibility; see C12-10 |
| C13-33 | Incident reporting organizations | External bodies that receive incident reports (e.g., CISA, sector sharing groups, regulators) | Reporting meets obligations and shares intelligence |
| C13-34 | FISMA requirements | US federal agencies must report incidents to CISA within required timeframes | Federal reporting obligation; see C11-19 |
| C13-35 | ISPs | Internet service providers as an outside party that can filter, trace, or block traffic | Key for upstream DDoS mitigation; see C13-06 |

## D. Prevention

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-36 | Preventing incidents | Reduce incident likelihood through risk assessment, patching, hardening, network and host security, malware defenses, and user awareness | Lowers the number of incidents but cannot eliminate them; see C01-32 to C01-38 |

## E. Detection and analysis details

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-37 | Attack vectors | Paths attacks use: external or removable media, attrition (brute force), web, email, impersonation, improper usage, loss or theft of equipment | The *route* of entry, not the attack goal |
| C13-38 | Signs of an incident | Precursors (signs an incident may occur in the future) and indicators (signs one has occurred or is occurring) | Precursor = future; indicator = present or past; see C11-13 |
| C13-39 | Precursor and indicator sources | Alerts (IDS/IPS, SIEM, antivirus), logs, publicly available information, and reports from people | Many sources; no single one is complete; see C11-02 |

## F. Containment, eradication, and recovery details

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-40 | Containment strategies | Choose a strategy by weighing potential damage, evidence preservation, service availability, time and resources, and duration | Balances stopping the attack against keeping evidence and services |
| C13-41 | Evidence gathering and handling | Collect and preserve evidence during response, documenting each step | Gather before wiping; keep the original intact; see C12-08 to C12-10 |
| C13-42 | Attack sources | Work out where the attack came from (attacker addresses, related infrastructure) | Source addresses can be spoofed; identifying the source must not delay containment |
| C13-43 | Eradication and recovery activities | Remove malware, disable compromised accounts, fix the exploited weakness, restore from clean sources, change credentials, and verify | Eradicate the cause before restoring; verify clean before returning to production |

## G. Post-incident activity

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C13-44 | Using collected incident data | Analyze incident data and metrics (counts, time spent, cost) to improve controls, plans, and training | Data-driven improvement; also supports resourcing decisions |
| C13-45 | Evidence retention | Keeping incident evidence for a defined period | Retention is set by policy and legal needs |
| C13-46 | Evidence retention policies | Rules for how long and how evidence is kept | Driven by legal, regulatory, and organizational requirements |
| C13-47 | Evidence retention use cases | Prosecution, internal discipline, audits and regulators, and lessons learned | The purpose determines retention length and handling rigor |
| C13-48 | Evidence retention best practices | Secure storage with access control, integrity checks, chain of custody, labeling, and secure disposal when expired | Protect integrity while kept; destroy securely afterward; see C07-18 |

---

## Chapter-specific question angles
- Put the SANS or NIST phases in order; or identify which phase a described action belongs to
- Compare lifecycles: SANS six steps vs NIST four phases
- Scenario → identify the incident type and the first response step
- Precursor vs indicator for a described sign
- Classify an event by attack vector (email, web, removable media, impersonation, and so on)
- Scenario → choose the containment strategy (stop spread vs preserve evidence vs keep service up)
- Scenario → who is contacted and through what channel (law enforcement, ISP, CISA, regulators)
- Plan vs policy; CSIRT composition; communications plan design
- Evidence retention: choose the retention approach for a given use case
- Neighbor discrimination: containment vs eradication vs recovery; post-incident review vs lessons learned; event vs incident
- "Which is NOT" a phase, attack vector, or CSIRT role
