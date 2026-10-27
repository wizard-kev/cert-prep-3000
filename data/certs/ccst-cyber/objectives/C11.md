# CCST Cybersecurity (100-160) | Chapter 11: Incident Handling

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 11 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 5.0 Incident Handling; regulations and compliance may also touch 4.0 and 1.0)

**Usage:** IDs (`C11-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Security monitoring and SIEM

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C11-01 | Security monitoring | Continuous collection and analysis of logs, events, and network activity to detect threats | Ongoing, not one-time; feeds detection and response; see C07-34 |
| C11-02 | SIEM | Security Information and Event Management: collects logs from many sources, correlates events, alerts, and retains data | Central collection plus correlation turns scattered events into meaningful alerts |
| C11-03 | SIEM hosting model | Where the SIEM runs: on-premises or in the cloud | A deployment choice with trade-offs in control, cost, and maintenance |
| C11-04 | On-prem SIEM | Organization hosts and maintains the platform | Full control and data stays local; higher upfront cost, maintenance, and scaling effort |
| C11-05 | Cloud SIEM | Vendor-hosted service | Elastic scaling and less maintenance; depends on connectivity, and data location may be a concern; see C11-17 |
| C11-06 | SIEM detection methods | Techniques the SIEM uses to spot suspicious activity | Combine several; no single method catches everything |
| C11-07 | Baseline analysis | Establish what normal activity looks like and compare current activity to it | The baseline is the reference; it must exist before deviations mean anything |
| C11-08 | Anomaly detection | Flags activity that deviates from the baseline or expected pattern | Can catch unknown threats but raises more false positives; contrast with signature-based; see C02-43 |
| C11-09 | Machine learning | Algorithms learn patterns from data to detect threats and reduce manual rule tuning | Learns from data rather than fixed rules; depends on good data and can still misclassify |
| C11-10 | AI integration | AI assists with triage, correlation, summarization, and prioritization | Augments analysts; results need human validation |
| C11-11 | UEBA | User and Entity Behavior Analytics: baselines users and devices and flags unusual behavior | Focuses on behavior of accounts and entities; helps find compromised accounts and insider threats; see C01-40 |
| C11-12 | Threat intelligence data | External feeds of known malicious IPs, domains, hashes, and attacker techniques | External context, versus an internal baseline; see C09-15 |
| C11-13 | IoC | Indicators of Compromise: observable evidence that a system may be compromised (malicious IPs, file hashes, domains, unusual changes) | Evidence of compromise; often delivered through threat intelligence |

## B. SOAR

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C11-14 | SOAR | Security Orchestration, Automation, and Response: coordinates tools and automates response workflows (playbooks) | SIEM detects and correlates; SOAR acts on what was detected |
| C11-15 | Orchestration vs automation | Orchestration coordinates multiple tools and tasks into a workflow; automation performs a single task without human action | Orchestration = many steps and tools; automation = one task |

## C. Regulations and compliance

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C11-16 | Regulations and compliance | Legal and industry requirements for protecting data; failure risks fines and legal action | External obligations, unlike internal policy; see C07-25 |
| C11-17 | Data locality | Requirement that data be stored or processed in specific geographic jurisdictions | About *where* data physically resides; affects cloud choices |
| C11-18 | FERPA | Family Educational Rights and Privacy Act: protects student education records (US) | Education records |
| C11-19 | FISMA | Federal Information Security Modernization Act: requires US federal agencies to run information security programs | Federal government systems |
| C11-20 | GLBA | Gramm-Leach-Bliley Act: financial institutions must protect customers' nonpublic personal information | Financial institutions |
| C11-21 | PCI DSS | Payment Card Industry Data Security Standard: protects cardholder data | An industry standard enforced through card-brand contracts, not a government law |
| C11-22 | Reporting | Formal reporting of incidents and compliance status to regulators, management, or auditors | Reporting to authorities and oversight; see C09-35 |
| C11-23 | Notifications | Informing affected individuals or customers (and sometimes regulators) after a breach, within required timeframes | Notifying the affected parties; deadlines vary by law |

---

## Chapter-specific question angles
- Scenario → choose the SIEM detection method (baseline, anomaly, UEBA, threat intelligence, IoC) that fits
- Trade-off scenario → on-prem vs cloud SIEM (control, cost, maintenance, data location)
- SIEM vs SOAR: which tool detects, which responds
- Orchestration vs automation for a described workflow
- Data type or organization → the regulation that applies (student records, card data, bank, federal agency)
- Scenario → data locality constraint and how it affects a cloud decision
- Reporting vs notification: who is informed, and why
- Neighbor discrimination: baseline vs anomaly detection; IoC vs threat intelligence feed; PCI DSS (standard) vs the others (laws)
- "Which is NOT" on SIEM capabilities or regulation scopes
