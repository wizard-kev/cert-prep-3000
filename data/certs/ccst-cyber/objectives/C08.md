# CCST Cybersecurity (100-160) | Chapter 8: Risk Management

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 8 (user-supplied list; grouping inferred from the flat list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 4.0 Vulnerability Assessment and Risk Management; data classification and posture assessment may also touch 1.0 and 2.0)

**Usage:** IDs (`C08-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Risk fundamentals and elements of risk

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C08-01 | Risk management | Ongoing process of identifying, assessing, and reducing risk to an acceptable level | Manages risk; it does not eliminate it, and it is a continuous cycle |
| C08-02 | Elements of risk | Risk exists when a threat can exploit a vulnerability to harm an asset | Remove any element (no asset, no weakness, no threat) and the risk changes or disappears |
| C08-03 | Vulnerabilities | Weaknesses that can be exploited (unpatched software, default credentials, misconfiguration, untrained users) | The *weakness*; threat is the who/what, exploit is the how; see C01-17, C01-32 |
| C08-04 | Threats | Potential sources of harm (attackers, malware, insiders, natural disasters) | Exists independently; becomes a risk when paired with a vulnerability |
| C08-05 | Exploits | Method, tool, or code that takes advantage of a vulnerability | The *how*; turns a vulnerability into a compromise |
| C08-06 | Assets | Anything of value to the organization (data, systems, people, reputation) | What is being protected; asset value drives the impact of loss |

## B. Risk analysis

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C08-07 | Risk analysis | Evaluating the likelihood and impact of identified risks, qualitatively (ratings) or quantitatively (numbers/currency) | Qualitative = low/medium/high labels; quantitative = measured values |
| C08-08 | Risk levels | Severity rating (e.g., low, medium, high, critical) derived from likelihood and impact | Combines both factors; a severe threat with low likelihood may still rate low |
| C08-09 | Risk matrix | Grid plotting likelihood against impact to assign a risk level | Two axes: likelihood and impact |
| C08-10 | Risk prioritization | Ranking risks so the highest-priority ones are addressed first | Based on risk level and asset value, not on what is easiest to fix |
| C08-11 | Data classifications | Labeling data by sensitivity (e.g., public, internal, confidential, restricted) to set handling and protection | Classification drives controls; labels vary by organization; see C02-01 |

## C. Risk mitigation

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C08-12 | Risk mitigation | Implementing controls that reduce the likelihood or impact of a risk | Reduces risk; some residual risk remains |
| C08-13 | Strategic response | Choose how to handle a risk: mitigate, transfer (e.g., insurance), avoid (stop the activity), or accept | Accepting must be a deliberate, documented decision; transfer shifts financial impact, not the risk itself |
| C08-14 | Action plan | Documented steps, owners, resources, and timeline for addressing prioritized risks | Specifies who does what and by when |
| C08-15 | Implementation and tracking | Carry out the plan and monitor progress, effectiveness, and residual risk | Work continues after deployment; verify, monitor, and reassess |

## D. Security assessments

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C08-16 | Security assessments | Structured evaluations of security posture | Umbrella for the next three items |
| C08-17 | Vulnerability assessments | Identify, classify, and report weaknesses, typically with scanners | Finds and lists; does *not* exploit |
| C08-18 | Penetration testing | Authorized, simulated attack that actively exploits weaknesses to show real impact | Exploits with permission, within an agreed scope |
| C08-19 | Posture assessment | Evaluate a device's or environment's security state against policy (patches, antivirus, configuration) | Compliance state; see C02-05, C04-21 |

## E. Change management

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C08-20 | Change management best practices | Structured process to request, review, test, approve, implement, and document changes | Reduces outages and security gaps caused by uncontrolled change |
| C08-21 | Documented business processes | Written procedures describing how business functions run | You cannot assess the impact of changing what is not documented |
| C08-22 | Change rollback plan (backout plan) | Predefined steps to restore the previous state if the change fails | Prepared *before* the change; two names, one concept; see C07-17 |
| C08-23 | Sandbox testing | Test the change in an isolated environment before production | Isolation keeps testing from affecting live systems |
| C08-24 | Responsible staff member | A named person accountable for the change | Accountability; a named individual, not a team |
| C08-25 | Change request forms | Formal record of a proposed change | The documented request and paper trail; holds the next four items |
| C08-26 | Purpose of change | The reason for the change (problem solved or business need) | Purpose = why |
| C08-27 | Scope of change | What the change touches (systems, users, locations, time window) | Scope = what and where; purpose = why |
| C08-28 | Risk review | Assess the risks the change introduces and how they will be handled | The change itself can create risk |
| C08-29 | Plan for change | Steps, schedule, resources, testing, and backout approach | Plan = how and when |
| C08-30 | Change board | Group that reviews and approves or rejects change requests | The approval authority; urgent changes may use an expedited path |
| C08-31 | User acceptance | End users or stakeholders confirm the change works as needed before it is closed | Confirmation by those who use the system, distinct from technical or sandbox testing |

---

## Chapter-specific question angles
- Scenario → classify each item as vulnerability, threat, exploit, or asset
- Given likelihood and impact → place the risk on a matrix or assign a level; or choose which risk to address first
- Scenario → choose the strategic response (mitigate, transfer, avoid, accept) and justify it
- Scenario → choose vulnerability assessment vs penetration testing vs posture assessment
- Change request form → identify the missing or misplaced element (purpose, scope, risk review, plan, approval)
- Put the change management steps in a sensible order, or identify what was skipped
- Neighbor discrimination: purpose vs scope; threat vs risk; mitigation vs transfer; sandbox testing vs user acceptance
- "Which is NOT" on risk elements, response strategies, or change request contents
