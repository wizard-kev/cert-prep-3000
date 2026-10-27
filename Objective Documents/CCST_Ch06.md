# CCST Cybersecurity (100-160) | Chapter 6: OS Basics and Security

**Source:** Sybex CCST Cybersecurity Study Guide, Ch. 6 (user-supplied list)
**File version:** v1 | **Domain tags:** provisional until checked against Cisco's blueprint (primary fit: 3.0 Endpoint Security Concepts; logging, syslog, and SIEM also touch 5.0 Incident Handling)

**Usage:** IDs (`C06-xx`) are the keys for the tracker and question log; never rename one, retire it instead. "Discriminator" = the one fact separating an objective from its look-alikes; test discriminators, not bare definitions. "See Cxx-yy" marks a cross-chapter link usable for mixed questions.

---

## A. Windows security

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C06-01 | Windows Defender Firewall | Built-in host-based firewall with separate Domain, Private, and Public profiles | Inbound blocked unless a rule allows it; outbound allowed by default; the active profile depends on network location; see C02-40 |
| C06-02 | Scripting | Automating admin tasks with PowerShell (.ps1), batch (.bat/.cmd), VBScript, or Python | Same tools attackers use ("living off the land"); PowerShell execution policy is a safety setting, not a security boundary |
| C06-03 | Windows security considerations | Hardening: daily use as a standard user, disable unused accounts and services, antimalware, disk encryption (BitLocker) | Goal is reducing attack surface with layered controls; see C01-38, C04-08 |
| C06-04 | NTFS permissions | File/folder permissions on NTFS volumes: Full control, Modify, Read & execute, List folder contents, Read, Write | Apply to both local and network access; cumulative across groups; Deny overrides Allow; Full control adds change permissions and take ownership over Modify |
| C06-05 | Local permissions | Access by a user logged on at the machine itself | Only NTFS permissions apply locally; share permissions are ignored |
| C06-06 | Share permissions | Read, Change, Full Control on a shared folder | Apply only to network access; when combined with NTFS, the *most restrictive* of the two is the effective access |
| C06-07 | File permission inheritance logic | Child files/folders inherit the parent's permissions by default; inheritance can be disabled | Precedence: explicit Deny > explicit Allow > inherited Deny > inherited Allow. Copy = takes destination's permissions; move within the same volume = keeps its permissions; move to another volume = takes destination's |
| C06-08 | Shared files and folders | Folders published to the network over SMB (TCP 445); hidden/administrative shares end in `$` (C$, ADMIN$) | `$` only hides a share from browsing; it does not secure it |
| C06-09 | UAC (User Account Control) | Prompts before actions that need administrative rights | Admins run with a standard token until elevation; admin sees a consent prompt, standard user sees a credential prompt; stops malware from silently gaining admin |
| C06-10 | Windows Updates | Windows Update delivers OS security, quality, and feature updates; WSUS/Intune centralize control | Monthly cumulative security updates (Patch Tuesday, second Tuesday) vs feature updates (new OS version) |
| C06-11 | Application patching | Third-party applications need their own update process | Patching the OS does not patch most third-party apps (browsers, PDF readers, runtimes); see C01-36 |
| C06-12 | Device drivers | Software that lets the OS communicate with hardware; runs in kernel mode | Driver = OS-side software; firmware = code on the device itself (see C01-37); 64-bit Windows requires signed kernel drivers; rollback restores the prior driver |

## B. macOS, Linux, and UNIX

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C06-13 | Mac App Store | Apple-reviewed, sandboxed app distribution | Gatekeeper controls apps from *outside* the store (identified/notarized developers); the App Store is the curated source |
| C06-14 | System updates | macOS Software Update; Linux package managers (`apt` on Debian/Ubuntu, `dnf`/`yum` on Red Hat/Fedora) | A Linux package manager updates the OS and repo-installed apps together; macOS updates come from Apple |
| C06-15 | Patch management | Ongoing process: inventory, identify, evaluate/test, approve, deploy, verify, document | A managed process, not a single update; test before production and keep a rollback plan |
| C06-16 | Firewall (macOS/Linux) | macOS application firewall (off by default; `pf` underneath); Linux netfilter managed via iptables/nftables or front-ends `ufw`/`firewalld` | macOS rules are per-application; Linux rules are port/address-based; ufw/firewalld are front-ends, not separate firewalls |
| C06-17 | Permissions (Linux/UNIX) | Read/write/execute for owner, group, and others; `chmod` (numeric 4/2/1, e.g., 754), `chown`; root = UID 0; `sudo` for elevation | Three digits = owner, group, others; execute on a directory means permission to enter it |

## C. Updates and life cycle

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C06-18 | Driver/firmware updates | Fix bugs and vulnerabilities in drivers and device firmware (BIOS/UEFI, NICs, storage) | Obtain from the vendor and verify integrity; interrupting a firmware update can brick the device (see C01-08) |
| C06-19 | OS life cycle | Release, mainstream support, extended support, end of support/end of life | After end of support, no security patches; unpatchable systems must be upgraded, replaced, or isolated (e.g., Windows 10 ended support Oct 14, 2025) |

## D. System logs and monitoring

| ID | Objective | Core idea | Discriminator |
|---|---|---|---|
| C06-20 | Event Viewer | Windows log viewer: Application, Security, System (plus Setup, Forwarded Events); levels Critical, Error, Warning, Information | Security log = logons and audited actions (Audit Success/Failure, e.g., 4624 logon, 4625 failed logon); System = OS components/drivers; Application = programs |
| C06-21 | Audit logs | Record security-relevant actions: who, what, when, from where; enabled by audit policy (Windows) or `auditd` (Linux) | Accountability trail; must be protected from tampering; see C04-10 |
| C06-22 | Syslog | Standard protocol for sending log messages, default UDP 514 | UDP 514 is cleartext and unreliable; TCP or TLS (6514) adds reliability/security |
| C06-23 | Syslog collector | Central server receiving syslog from many devices | Centralized copy survives if a device is compromised or wiped; requires consistent time (NTP, see C03-09) |
| C06-24 | Syslog messages | Cisco format: sequence, timestamp, `%FACILITY-SEVERITY-MNEMONIC: description` (e.g., `%LINK-3-UPDOWN`) | The number in the middle is the severity level |
| C06-25 | Logging / severity levels | 0 Emergency, 1 Alert, 2 Critical, 3 Error, 4 Warning, 5 Notification, 6 Informational, 7 Debugging | Lower number = more severe; setting level N logs N and everything more severe (0 to N) |
| C06-26 | Identifying anomalies | Compare log activity to a baseline: off-hours logons, repeated failed logons, new admin accounts, unusual traffic | Anomaly needs a baseline; a cleared Security log (Event ID 1102) is itself a red flag; see C02-43 |
| C06-27 | SIEM | Aggregates, normalizes, and correlates logs from many sources; alerts, dashboards, retention | Correlation across sources; a syslog collector stores logs, a SIEM analyzes them |

---

## Chapter-specific question angles
- Scenario with share + NTFS permissions → compute the effective access (network vs local)
- File copied or moved → predict which permissions it ends up with
- Syslog message or `logging trap` level → identify the severity, or which messages get logged
- Log excerpt or Event ID → identify the anomaly or which Windows log holds it
- Scenario → choose the control (UAC, firewall profile, patch, upgrade an end-of-support OS)
- Linux `ls -l` output or `chmod` number → state who can do what
- Neighbor discrimination: NTFS vs share permissions; driver vs firmware; OS patch vs application patch; syslog collector vs SIEM; Gatekeeper vs App Store; consent vs credential prompt
- "Which is NOT" on severity levels, Event Viewer logs, or patch-management steps
