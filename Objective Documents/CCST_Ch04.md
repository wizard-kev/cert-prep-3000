# CCST Cybersecurity (100-160) | Chapter 4: Network Device Access

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 4 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (AAA, MFA, password policy fit 1.0 Essential Security Principles; NAC, 802.1X, BYOD fit 2.0 Basic Network Security Concepts)

**Usage:** IDs (`C04-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See C01-xx / C02-xx" marks a cross-chapter link usable for mixed questions.

---

## A. Local authentication and the iAAA model

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C04-01 | Local authentication | Accounts stored on the device itself, created in the CLI (`username NAME privilege 15 secret PASS`) and applied to lines with `login local` | Credentials live on each device; does not scale; `secret` is hashed, `password` is not |
| C04-02 | iAAA model | Identification, Authentication, Authorization, Accounting | Who are you? Prove it. What may you do? What did you do? |
| C04-03 | Authentication | Verifying a claimed identity using one or more factors (know, have, are) | Proves identity; says nothing yet about permissions |
| C04-04 | MFA | Requires two or more *different* factor categories | Two passwords is not MFA; factors must come from different categories |
| C04-05 | MFA methods | Email, SMS, voice call, time-based hardware/software tokens | Time-based tokens are generally stronger; SMS/voice/email codes can be intercepted or redirected |
| C04-06 | Authorization | Determines what an authenticated user may access or do | Happens after authentication |
| C04-07 | Identity and Access Management (IAM) | Processes and tools that manage identities and their access across their lifecycle | The umbrella program; AAA is one mechanism inside it |
| C04-08 | Least privilege | Grant only the access needed to do the job | Limits damage from mistakes, malware, and insiders; see C01-40 |
| C04-09 | RBAC | Permissions attach to roles; users get access through their role | Role-based, not per-individual assignment |
| C04-10 | Accounting | Records who did what and when (logins, commands, session data) | After-the-fact audit trail; enables traceability |
| C04-11 | RADIUS | Centralized AAA over UDP (1812 auth, 1813 accounting); encrypts only the password in the request | Open standard; combines authentication and authorization; typical for network access (802.1X, Wi-Fi, VPN) |
| C04-12 | TACACS+ | Centralized AAA over TCP 49; encrypts the entire payload | Cisco-originated; separates authentication, authorization, accounting; typical for device administration |
| C04-13 | Configuring iAAA | Enable AAA, define the server, build method lists for authentication/authorization/accounting, apply them to lines | Method list order matters; fallback to local happens when the server is unreachable, not when it rejects |
| C04-14 | RADIUS login process | User credentials go to the access device, which sends an Access-Request to the RADIUS server and acts on Access-Accept, Access-Reject, or Access-Challenge | The access device (switch/AP) is the RADIUS client, not the user's endpoint |

## B. Password policy

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C04-15 | Password length and complexity | Longer passwords with mixed character types resist guessing | Length adds more strength than complexity alone; see C01-29, C01-30, C01-33 |
| C04-16 | Password lockout | Locks an account after a set number of failed attempts | Counters online brute force; can itself be abused to lock out legitimate users |

## C. Network Access Control (802.1X)

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C04-17 | 802.1X | Port-based access control: a port passes only authentication traffic until the device authenticates | The port stays blocked until success; see C02-04 |
| C04-18 | 802.1X components | Supplicant (client), authenticator (switch/WAP), authentication server (RADIUS) | The authenticator enforces; the server decides |
| C04-19 | NAC process | Device connects, is identified and assessed, then policy sets its access level (full, restricted, quarantine, deny) | Outcome is policy-driven and need not be all-or-nothing |
| C04-20 | Profiling | Identifies what a device *is* (type/class) from observed attributes | Useful for devices that cannot run a supplicant (printers, IoT) |
| C04-21 | Posturing (posture assessment) | Checks a device's health and compliance (patches, antivirus, configuration) | Health vs identity vs type; see C02-05 |

## D. BYOD

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C04-22 | BYOD | Personally owned devices accessing organizational resources | Unmanaged and varied, so needs NAC, posture checks, and segmentation |
| C04-23 | Guest network isolation | Guests placed on a separate segment with internet-only access | Isolation from internal resources; see C02-06 |
| C04-24 | Captive portal | Web page that intercepts a new user's first request and requires login or acceptance before granting access | A gate for guest/BYOD onboarding, not encryption of wireless traffic |

---

## Chapter-specific question angles
- Scenario → choose RADIUS vs TACACS+ (network access vs device administration)
- Log or complaint → identify which "A" in iAAA applies
- Classify an example as a factor type, and decide whether it counts as MFA
- Config fragment → identify what it does (local login vs AAA method list)
- Order the steps of the RADIUS login or NAC process
- Name the 802.1X component from a description
- Neighbor discrimination: authentication vs authorization vs accounting; profiling vs posturing; RADIUS vs TACACS+; guest isolation vs BYOD onboarding
- "Which is NOT" on MFA factors or password-policy controls
