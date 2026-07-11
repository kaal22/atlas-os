# Atlas OS — Product Specification

> **Working title:** Atlas OS  
> **Document:** `product.md`  
> **Version:** 0.2.0  
> **Status:** Build specification — acquisition map added  
> **Date:** 11 July 2026  
> **Primary platform:** x86-64 laptops, desktops and mini PCs  
> **Base system:** Debian 13 Stable  
> **Primary distribution format:** Bootable hybrid ISO  
> **Secondary formats:** OEM disk image, recovery ISO and software installer  
> **Product category:** Offline-first AI agent operating environment and knowledge appliance

---

## 1. Executive Summary

Atlas OS is a secure, offline-first operating system that turns a compatible computer into a private AI workstation, knowledge server and multi-agent digital assistant.

It combines:

- A complete Debian-based operating system.
- A consumer-friendly graphical installer.
- Local AI models running through a hardware-aware model runtime.
- Multiple specialised AI agents.
- Offline document search and retrieval-augmented generation.
- Offline knowledge libraries, maps and education resources.
- Secure local access from phones, tablets and other computers.
- Encrypted storage, backups, snapshots and factory recovery.
- Signed operating system, application and content updates.
- Optional online and cloud-model capabilities that remain disabled until the user explicitly enables them.

Atlas OS is derived in part from the open-source Project N.O.M.A.D. platform, but it is not intended to be a cosmetic rebrand. Project N.O.M.A.D. supplies useful offline content-management and application capabilities. Atlas OS adds the operating system, installer, identity and permissions layer, agent runtime, hardware detection, model routing, security boundary, update infrastructure, recovery system, commercial packaging and end-user experience.

The product should feel like a dedicated appliance rather than a Linux distribution assembled from unrelated components. A non-technical customer must be able to install Atlas OS, choose a use profile, select recommended AI and content packs, and begin using the system without opening a terminal.

---

## 2. Product Vision

### 2.1 Vision statement

> Give people a private, dependable digital intelligence system that remains useful when the cloud, subscriptions or internet connection are unavailable.

### 2.2 Product promise

Atlas OS keeps the user’s AI, documents, maps, learning resources, notes and essential knowledge available locally. Core functionality continues to work without an internet connection and without an active subscription.

### 2.3 Positioning

Atlas OS is not positioned as:

- Another general-purpose Linux distribution.
- A survival-themed collection of downloaded files.
- A chatbot wrapped around an open-source model.
- A renamed Project N.O.M.A.D. installation.
- A replacement for professional medical, legal or emergency services.
- A cloud-first SaaS product that happens to offer an offline mode.

Atlas OS is positioned as:

> A private offline AI and knowledge operating environment for travel, remote living, education, field work, personal knowledge and resilient computing.

---

## 3. Strategic Thesis

Project N.O.M.A.D. proves demand for a self-contained offline knowledge and AI platform. However, its upstream experience is still aimed primarily at technically capable users:

- Installation is terminal-based.
- It runs on top of an existing Debian-family operating system.
- The management application is accessed through a browser.
- The platform does not currently include user authentication.
- The management layer uses Docker-outside-of-Docker orchestration.
- Content, models and tools can have different hardware and licensing requirements.
- The customer is responsible for installation, networking, security, updates and recovery.

Atlas OS turns those components into a reproducible commercial product.

The defensible value is not the existence of an installation script. The defensible value is:

- Safe defaults.
- A unified user experience.
- A secure agent execution model.
- Hardware-aware AI configuration.
- Curated and licensed content.
- Signed and tested updates.
- Recovery and migration.
- Compatibility testing.
- Certified hardware.
- Documentation and support.
- A trusted product brand.

---

## 4. Product Principles

Every architectural and product decision must follow these principles.

### P-01: Offline is the default state

Core features must work without internet access after installation and content provisioning.

### P-02: Local-first privacy

User data, agent memory, document embeddings, notes and conversations remain local unless the user knowingly enables an external provider.

### P-03: Safe before autonomous

Agents may reason freely, but actions with meaningful consequences require explicit permissions, policy checks and, where appropriate, user approval.

### P-04: No terminal required

Normal installation, configuration, updates, backups, recovery and content management must be available through the graphical interface.

### P-05: Reproducible releases

Every ISO release must pin its operating-system packages, application versions, container digests, model metadata and content manifests.

### P-06: Recoverable by design

The user must be able to roll back a failed update, restore a backup or factory-reset the operating system without losing personal data.

### P-07: Modular, not monolithic

The operating system, agent runtime, applications, AI models and content packs must be versioned and updated separately.

### P-08: Hardware-aware intelligence

The system must detect available CPU, RAM, GPU, VRAM, storage and power characteristics and make safe recommendations.

### P-09: Honest capability boundaries

The interface must distinguish local knowledge, retrieved sources, model inference, online search and agent actions. It must not imply certainty when none exists.

### P-10: Upstream-compatible derivative

Project N.O.M.A.D. integration should be maintained through a controlled upstream branch, adapter layer and documented patches rather than an untraceable permanent fork.

---

## 5. Goals

### 5.1 Primary launch goals

1. Produce a signed x86-64 hybrid ISO that can boot in UEFI systems and install onto supported laptops, desktops and mini PCs.
2. Provide a polished live environment and Calamares-based graphical installation flow.
3. Start Atlas OS into a guided first-run experience after installation.
4. Automatically detect hardware and recommend appropriate local AI profiles.
5. Provide a private multi-agent workspace powered by local models.
6. Integrate offline document search, Kiwix libraries, offline maps and Kolibri learning content.
7. Add user authentication, role-based access and encrypted local secrets.
8. Restrict agent tools through a policy-enforced execution gateway.
9. Allow trusted devices to access Atlas through a private local portal.
10. Provide signed system, application, model-metadata and content-pack updates.
11. Provide one-click backups, rollback snapshots and factory recovery.
12. Package the product for software download, bootable USB and preinstalled hardware sales.

### 5.2 Secondary goals

- Support optional OpenAI-compatible remote model providers.
- Support an optional companion progressive web app.
- Support offline voice input and speech output.
- Support family, education, travel and field-team operating profiles.
- Support headless “Atlas Node” installations.
- Support managed business deployments in a later edition.

---

## 6. Non-Goals for Version 1

Version 1 will not attempt to:

- Replace Windows or macOS for every use case.
- Support every Linux desktop package.
- Ship a custom Linux kernel.
- Support ARM64 installation media.
- Guarantee support for every NVIDIA, AMD or Intel GPU.
- Provide unattended agents with unrestricted shell or root access.
- Provide unrestricted internet-facing remote administration.
- Build a public marketplace that runs unreviewed third-party agents.
- Include every available Kiwix archive, model or map in the core ISO.
- Train foundation models.
- Provide medical diagnosis, legal advice or emergency-response guarantees.
- Implement enterprise fleet management in the consumer release.
- Require a subscription for continued access to locally installed features.

---

## 7. Target Users

### 7.1 Traveller / digital nomad

Needs private AI, documents, maps and useful knowledge while travelling across unreliable networks.

Key needs:

- Local AI without recurring API charges.
- Travel document vault.
- Regional maps and language resources.
- Safe use on hotel and public Wi-Fi.
- Phone access through a private hotspot.
- Battery-aware model selection.

### 7.2 Vanlife / motorhome / overlanding user

Needs maps, repair references, manuals, planning, offline media and resilient access from multiple devices.

Key needs:

- Vehicle and equipment manuals.
- Journey packs.
- Local network portal.
- Low-power mode.
- External-drive content.
- Offline route and place information.

### 7.3 Privacy-conscious individual

Wants an AI assistant that does not upload personal documents or conversations by default.

Key needs:

- Full-disk encryption.
- Local model execution.
- Transparent provider status.
- Fine-grained permissions.
- Local backups.
- No mandatory account.

### 7.4 Family / home educator

Needs shared knowledge, educational content and age-appropriate accounts.

Key needs:

- Multiple profiles.
- Parent and child roles.
- Kolibri integration.
- Shared and private memory scopes.
- Content controls.
- Learning and research agents.

### 7.5 Field worker / charity / remote team

Needs a portable local server for documents, procedures, training and structured tasks.

Key needs:

- Organisation content packs.
- Team accounts.
- Controlled agent workflows.
- Audit logs.
- Deployment templates.
- Backup and device replacement.

### 7.6 Preparedness and resilience customer

Wants reliable access to practical information and personal documents during outages or loss of connectivity.

Key needs:

- Offline operation.
- Essential-reference collections.
- Emergency dashboard.
- Low-power operation.
- Print/export options.
- Clear warnings that material is reference information, not a professional service.

---

## 8. Jobs to Be Done

### JTBD-01

When I have no internet connection, I want to ask questions across my downloaded knowledge and personal files so I can still make progress.

### JTBD-02

When I am travelling, I want my maps, travel documents, manuals and AI assistant available from my laptop and phone.

### JTBD-03

When I add documents, I want Atlas to organise and index them locally without requiring technical configuration.

### JTBD-04

When I ask an agent to perform a task, I want to understand which tools it will use and approve consequential actions.

### JTBD-05

When a software update fails, I want the system to return automatically to the previous working state.

### JTBD-06

When I replace or reinstall my computer, I want to restore my identity, agents, knowledge and settings from an encrypted backup.

### JTBD-07

When my hardware cannot run a large model, I want Atlas to choose a smaller suitable model rather than freezing or failing.

### JTBD-08

When I connect to a public network, I want Atlas to stop exposing local services automatically.

---

## 9. Product Editions

The product architecture is shared across all editions. Editions alter enabled features, support and licensed content rather than maintaining separate codebases.

### 9.1 Atlas Personal

Includes:

- Core operating system.
- Local AI assistant.
- Three configurable agents.
- Personal document vault.
- Knowledge library.
- Offline maps.
- Local backup and restore.
- One primary user plus guest mode.

### 9.2 Atlas Explorer

Adds:

- Journey mode.
- Regional content packs.
- Travel and vehicle agents.
- Private hotspot portal.
- External SSD content libraries.
- Low-power mode.
- Multi-device access.

### 9.3 Atlas Family

Adds:

- Multiple users.
- Parent and child roles.
- Family knowledge spaces.
- Kolibri integration.
- Learning agent.
- Content and time controls.
- Per-user private memory.

### 9.4 Atlas Field

Adds:

- Team roles.
- Organisation workspaces.
- Signed organisation content packs.
- Workflow templates.
- Extended audit retention.
- Deployment and recovery tooling.
- Optional managed updates.

### 9.5 Atlas Node

A headless or kiosk-oriented build for mini PCs and small local servers.

Adds:

- Browser-first administration.
- Access-point mode.
- No full desktop required.
- Remote local-network setup.
- Optional UPS and power-event monitoring.

---

## 10. Distribution Formats

### 10.1 Hybrid installation ISO

Filename pattern:

```text
atlas-os-<version>-amd64.iso
```

Capabilities:

- UEFI boot.
- Legacy BIOS boot where practical.
- Live “Try Atlas” session.
- Graphical installation.
- Hardware compatibility report.
- Optional online or offline installation.
- Checksum and signature verification.

### 10.2 OEM disk image

Filename pattern:

```text
atlas-os-<version>-oem-amd64.img.zst
```

Used for prebuilt systems.

Requirements:

- No customer identity embedded.
- First-boot hardware expansion.
- Regenerated machine ID.
- Regenerated SSH host keys if SSH is enabled.
- Unique application and encryption secrets.
- OEM quality-control mode.
- Final customer onboarding on first boot.

### 10.3 Recovery ISO

Filename pattern:

```text
atlas-recovery-<version>-amd64.iso
```

Capabilities:

- Boot repair.
- Filesystem checks.
- Decryption prompt.
- Snapshot rollback.
- Backup restore.
- Reinstallation while preserving the Atlas data partition.
- Hardware diagnostics.
- Export diagnostic bundle.

### 10.4 Existing-Linux installer

A later secondary product:

```text
atlas-install.run
```

This installs the Atlas application and agent stack on a supported Debian-family system but does not provide the full appliance guarantees of Atlas OS.

---

## 11. Customer Experience

### 11.1 Installation journey

1. Customer downloads the ISO or receives a bootable USB.
2. Customer verifies the checksum through the download page or Atlas USB tool.
3. Customer boots the device.
4. Live environment displays:
   - Try Atlas.
   - Install Atlas.
   - Hardware check.
   - Recovery tools.
5. Installer guides the customer through:
   - Language.
   - Keyboard.
   - Timezone.
   - Network.
   - Storage.
   - Encryption.
   - User account.
   - Optional recovery key export.
6. Atlas installs the tested OS payload.
7. Device reboots.
8. First-run wizard analyses hardware.
9. Customer selects a profile:
   - Personal.
   - Travel.
   - Family.
   - Off-grid.
   - Private AI workstation.
   - Field team.
10. Atlas recommends an AI profile and estimated storage.
11. Customer selects content packs.
12. Atlas provisions containers, models and indexes.
13. Dashboard opens with a guided tour.

### 11.2 Daily experience

The default home screen contains:

- Ask Atlas.
- Agents.
- Knowledge.
- Documents.
- Maps.
- Learn.
- Notes.
- Tasks.
- Device sharing.
- Backups.
- System health.
- Settings.

The user should not normally see:

- Docker terminology.
- Container names.
- Ports.
- Compose files.
- Model quantisation codes.
- Linux package errors.
- Raw stack traces.

Technical detail remains available in an Advanced section and downloadable diagnostic reports.

---

## 12. High-Level System Architecture

```text
┌────────────────────────────────────────────────────────────────┐
│                         Atlas Shell                            │
│ Desktop, kiosk launcher, PWA, notifications, accessibility    │
└───────────────────────────────┬────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────┐
│                     Atlas Command Centre                      │
│ Home, agents, knowledge, maps, content, backups, settings      │
└──────────────┬────────────────┬────────────────┬───────────────┘
               │                │                │
┌──────────────▼───────┐ ┌──────▼────────┐ ┌────▼──────────────┐
│ Atlas Agent Runtime  │ │ Identity/Auth │ │ Content Manager   │
│ Planner, memory,     │ │ Roles, policy │ │ Packs, licences,  │
│ tools, tasks         │ │ sessions      │ │ downloads, USB    │
└──────────────┬───────┘ └──────┬────────┘ └────┬──────────────┘
               │                │                │
┌──────────────▼────────────────▼────────────────▼───────────────┐
│                       Atlas Policy Gateway                    │
│ Tool registry, capability tokens, approvals, audit, budgets   │
└──────┬──────────────┬──────────────┬───────────────┬──────────┘
       │              │              │               │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼────────┐ ┌────▼──────────┐
│ Knowledge   │ │ Model      │ │ System      │ │ App / NOMAD   │
│ Service     │ │ Router     │ │ Daemon      │ │ Adapter       │
│ Qdrant/RAG  │ │ Ollama/API │ │ Privileged  │ │ Containers    │
└──────┬──────┘ └─────┬──────┘ └────┬────────┘ └────┬──────────┘
       │              │              │               │
┌──────▼──────────────▼──────────────▼───────────────▼──────────┐
│                    Debian 13 Host Platform                    │
│ LUKS, Btrfs/ext4, systemd, Docker, NetworkManager, firewall   │
└────────────────────────────────────────────────────────────────┘
```

---

## 13. Base Operating System

### 13.1 Base

- Debian 13 Stable.
- x86-64 architecture.
- Debian `live-build` for ISO generation.
- Calamares for graphical installation.
- KDE Plasma as the desktop environment (X11 session by default; Wayland hidden).
- SDDM as the display manager (`DisplayServer=x11`).
- NetworkManager for network and hotspot management.
- PipeWire for audio.
- Flatpak disabled or omitted from the initial appliance build unless explicitly required.
- Docker Engine and Docker Compose plugin for managed applications.
- AppArmor enabled.
- Full-disk encryption offered by default.

### 13.2 Desktop modes

Atlas supports three presentation modes:

#### Appliance mode

Default for ordinary users.

- Atlas Command Centre launches at login.
- Desktop icons are minimal.
- System settings are curated.
- Advanced Linux administration is hidden but not removed.

#### Desktop mode

For users who want a conventional computer.

- File manager.
- Browser.
- Office suite.
- PDF viewer.
- Media player.
- Terminal available under Advanced Tools.

#### Node mode

For headless systems.

- No local desktop requirement.
- Local setup portal.
- Console recovery interface.
- Browser access from trusted devices.

### 13.3 Preinstalled desktop applications

Version 1 should include only mature, supportable applications:

- Firefox ESR or a hardened Chromium-family browser.
- LibreOffice.
- Document viewer.
- Archive manager.
- Media player.
- Text editor.
- Screenshot utility.
- File manager.
- Atlas diagnostics.
- Atlas recovery launcher.

The package set must remain intentionally small.

---

## 14. ISO Build System

### 14.1 Repository layout

```text
atlas-os/
├── product.md
├── README.md
├── Makefile
├── VERSION
├── auto/
│   ├── config
│   ├── build
│   └── clean
├── config/
│   ├── archives/
│   ├── bootloaders/
│   ├── hooks/
│   ├── includes.binary/
│   ├── includes.chroot/
│   ├── package-lists/
│   ├── packages.chroot/
│   └── preseed/
├── calamares/
│   ├── branding/
│   ├── modules/
│   ├── settings.conf
│   └── slideshow/
├── packages/
│   ├── atlas-branding/
│   ├── atlas-shell/
│   ├── atlas-command-centre/
│   ├── atlas-agent-runtime/
│   ├── atlas-policy-gateway/
│   ├── atlas-system-daemon/
│   ├── atlas-content-manager/
│   ├── atlas-model-manager/
│   ├── atlas-backup/
│   ├── atlas-updater/
│   └── atlas-firstboot/
├── containers/
│   ├── compose/
│   ├── manifests/
│   ├── payload/
│   └── scripts/
├── content/
│   ├── schemas/
│   ├── catalogues/
│   └── licences/
├── models/
│   ├── profiles/
│   ├── licences/
│   └── manifests/
├── upstream/
│   ├── project-nomad/
│   ├── patches/
│   └── adapter/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── installer/
│   ├── vm/
│   ├── hardware/
│   └── security/
├── scripts/
│   ├── build-debs.sh
│   ├── build-containers.sh
│   ├── export-payload.sh
│   ├── build-iso.sh
│   ├── build-oem-image.sh
│   ├── sign-release.sh
│   └── test-release.sh
└── .github/
    └── workflows/
```

### 14.2 Build requirements

A release build must:

- Run from a clean Debian build environment.
- Pin the Debian release and repository snapshot.
- Pin all custom package versions.
- Pin all container images by digest.
- Generate a software bill of materials.
- Generate a licence manifest.
- Produce SHA-256 and SHA-512 checksums.
- Sign release metadata.
- Boot-test the ISO.
- Install-test the ISO.
- Run post-install health checks.
- Fail closed if any required asset is missing or unverified.

### 14.3 Release artefacts

Each release directory must contain:

```text
atlas-os-1.0.0-amd64.iso
atlas-os-1.0.0-amd64.iso.sha256
atlas-os-1.0.0-amd64.iso.sha512
atlas-os-1.0.0-amd64.iso.sig
atlas-os-1.0.0-oem-amd64.img.zst
atlas-recovery-1.0.0-amd64.iso
atlas-os-1.0.0-sbom.spdx.json
atlas-os-1.0.0-licences.tar.zst
atlas-os-1.0.0-release.json
atlas-os-1.0.0-source-manifest.json
```

---

## 15. Project N.O.M.A.D. Integration Strategy

### 15.1 Role of upstream

Project N.O.M.A.D. provides or manages capabilities including:

- Kiwix offline libraries.
- Ollama-based local AI support.
- Qdrant-backed retrieval.
- Kolibri.
- Offline maps.
- Additional containerised applications.
- Content management and service lifecycle operations.

### 15.2 Integration rule

Atlas must not depend on running the upstream internet installer during customer installation.

Instead, the release pipeline must:

1. Select a reviewed upstream tag or commit.
2. Record it in `source-manifest.json`.
3. Apply Atlas patches in a deterministic order.
4. Build a pinned Atlas-compatible image.
5. Export all required images into the offline installation payload.
6. Run compatibility and migration tests.
7. Publish attribution and modification notices.

### 15.3 Upstream directory policy

```text
upstream/project-nomad/
```

is read-only in normal development.

Atlas changes are stored in:

```text
upstream/patches/
upstream/adapter/
```

A deliberate rebase process updates the upstream source.

### 15.4 Replacement boundaries

Atlas may initially reuse the upstream Command Center behind an Atlas shell. Over time, Atlas should replace or isolate the following boundaries:

- Authentication and sessions.
- Host-level privileged operations.
- Direct Docker-socket access from the browser-facing application.
- Update control.
- Network exposure.
- Secrets management.
- Agent runtime.
- Device and user management.
- Commercial content catalogue.

### 15.5 Attribution

The installed product must include:

- Project N.O.M.A.D. copyright notice.
- Apache License 2.0.
- Source commit identifier.
- Description of material modifications.
- Link or bundled source-offer information where required.
- Separate third-party licence notices.

Atlas branding must not imply endorsement by Crosstalk Solutions.

---

## 16. Core Atlas Services

### 16.1 Atlas Command Centre

Purpose:

- Primary graphical user interface.
- Responsive local web application.
- Desktop shell and mobile portal.

Suggested stack:

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- Accessible component library.
- Server-sent events or WebSockets for progress.
- Local API gateway.

Core routes:

```text
/
 /ask
 /agents
 /agents/:id
 /tasks
 /knowledge
 /documents
 /maps
 /learn
 /notes
 /content
 /devices
 /backups
 /system
 /settings
 /admin
```

### 16.2 Atlas Agent Runtime

Purpose:

- Manage agent definitions.
- Route model requests.
- Manage planning and task execution.
- Apply tool permissions.
- Store memory.
- Coordinate multi-agent hand-offs.
- Maintain task state.
- Produce user-readable action plans and audit records.

Recommended implementation:

- TypeScript service for API and event orchestration.
- Python worker service where mature AI/RAG libraries provide a clear advantage.
- PostgreSQL or the existing MySQL database may be used initially, but Atlas should avoid unnecessary duplicate databases.
- Redis-backed durable work queue.
- Explicit state-machine execution rather than uncontrolled recursive agent loops.

### 16.3 Atlas Policy Gateway

Purpose:

- Sit between every model/agent and every tool.
- Enforce permissions independently from model instructions.
- Issue short-lived capability tokens.
- Require approval for sensitive operations.
- Rate-limit and budget actions.
- Log every tool invocation.
- Block prompt-originated privilege escalation.

The model must never call the operating system, Docker socket or host shell directly.

### 16.4 Atlas Model Router

Purpose:

- Discover local and remote model providers.
- Select a model based on task, hardware and privacy policy.
- Manage model installation and removal.
- Provide model health checks.
- Enforce context and concurrency limits.
- Expose a stable internal OpenAI-compatible interface.

Providers:

- Local Ollama.
- Optional remote Ollama.
- Optional OpenAI-compatible API.
- Future specialised inference engines through adapters.

### 16.5 Atlas Knowledge Service

Purpose:

- Ingest user documents.
- Ingest selected offline resources.
- Extract text and metadata.
- Chunk and embed content.
- Search vectors and metadata.
- Return source-grounded context.
- Manage index versions.
- Snapshot and restore Qdrant collections.

### 16.6 Atlas System Daemon

Purpose:

- Perform narrowly defined privileged host operations.
- Replace broad browser-facing Docker socket access.

Example API capabilities:

```text
system.health.read
system.power.profile.set
network.hotspot.enable
network.hotspot.disable
storage.mount
storage.unmount
backup.create
backup.restore
update.stage
update.apply
update.rollback
container.install
container.start
container.stop
container.remove
logs.bundle.create
```

Security requirements:

- Runs as root only where required.
- Listens on a Unix domain socket.
- Rejects arbitrary commands.
- Uses strict typed request schemas.
- Requires signed capability tokens from the Policy Gateway.
- Writes append-only audit entries.
- Uses systemd hardening directives.
- Has no direct internet-facing listener.

### 16.7 Atlas Content Manager

Purpose:

- Display available knowledge, map, model and education packs.
- Calculate storage requirements.
- Download or import packs.
- Verify checksums and signatures.
- Mount packs.
- Index compatible content.
- Apply updates.
- Remove superseded files safely.
- Display licences and attribution.

### 16.8 Atlas Backup Service

Purpose:

- Back up Atlas configuration, users, agent memory, documents, content manifests, database data and vector snapshots.
- Encrypt backups.
- Verify restore integrity.
- Support full and selective restore.
- Support migration to replacement hardware.

### 16.9 Atlas Updater

Purpose:

- Manage OS, application, container and content updates.
- Stage and verify payloads.
- Create rollback snapshots.
- Run pre-flight and post-flight checks.
- Roll back automatically on failure.

---

## 17. AI Agent System

### 17.1 Agent philosophy

An Atlas agent is not merely a system prompt. It is a versioned package containing:

- Identity and purpose.
- Instruction hierarchy.
- Allowed model profiles.
- Tool permissions.
- Memory scopes.
- Knowledge scopes.
- Workflow templates.
- Approval rules.
- Resource limits.
- User interface metadata.
- Tests.
- Version and publisher identity.

### 17.2 Agent package format

```text
my-agent.atlas-agent
```

Internally:

```text
manifest.yaml
instructions/
  system.md
  planning.md
  safety.md
tools/
  permissions.yaml
knowledge/
  sources.yaml
workflows/
  *.yaml
ui/
  icon.svg
  description.md
tests/
  scenarios.yaml
LICENSE
SIGNATURE
```

Example manifest:

```yaml
schema: atlas.agent/v1
id: atlas.travel
name: Travel Agent
version: 1.0.0
publisher: atlas
description: Plans journeys using local maps, user documents and selected online tools.
models:
  preferred_profiles:
    - balanced
    - advanced
  minimum_context: 8192
memory:
  read:
    - user.profile
    - workspace.travel
  write:
    - workspace.travel
knowledge:
  scopes:
    - user.travel_documents
    - content.maps
    - content.travel
tools:
  allow:
    - knowledge.search
    - maps.search
    - documents.read
    - notes.write
    - tasks.create
  deny:
    - shell.execute
    - system.package.install
approvals:
  always:
    - documents.delete
    - network.external_request
limits:
  max_steps: 20
  max_tool_calls: 40
  max_runtime_seconds: 600
```

### 17.3 Built-in launch agents

#### Atlas Guide

The default general assistant.

Capabilities:

- Answer questions.
- Search local knowledge.
- Explain system features.
- Create notes and tasks.
- Hand work to specialist agents.
- Never receive privileged system permissions.

#### Research Agent

Capabilities:

- Search local knowledge libraries.
- Search personal documents.
- Optionally search the web when online and authorised.
- Build source-linked research reports.
- Distinguish local, personal and online sources.

#### Document Agent

Capabilities:

- Import, classify and summarise documents.
- Extract tasks, dates and entities.
- Create document collections.
- Compare versions.
- Draft derived material.
- Require approval before renaming, moving or deleting files.

#### Travel Agent

Capabilities:

- Search installed maps and travel packs.
- Organise itineraries.
- Prepare journey checklists.
- Retrieve travel documents.
- Build destination content-download plans.
- Use live online data only when enabled.

#### Learning Agent

Capabilities:

- Work with Kolibri and offline educational material.
- Generate study plans.
- Explain material at configurable reading levels.
- Track local progress.
- Respect child-profile restrictions.

#### Technical Agent

Capabilities:

- Search installed technical manuals.
- Inspect non-sensitive system diagnostics.
- Guide troubleshooting.
- Propose commands.
- Run only pre-approved diagnostic tools.
- Never obtain unrestricted root shell access.

#### System Steward

A tightly constrained maintenance agent.

Capabilities:

- Read system health.
- Explain update and storage issues.
- Recommend corrective actions.
- Invoke allowlisted repair workflows after approval.
- Cannot construct arbitrary host commands.
- All actions require an auditable workflow definition.

#### Knowledge Curator

Capabilities:

- Recommend content packs.
- Detect duplicate documents.
- Suggest tags and collections.
- Monitor index health.
- Rebuild approved indexes.
- Report licences and storage impact.

### 17.4 Custom agents

Users can create custom agents through a guided builder.

Required fields:

- Name.
- Purpose.
- Knowledge access.
- Memory access.
- Tool access.
- Confirmation policy.
- Preferred model profile.
- Workspace.
- Icon.

The builder must translate ordinary-language choices into explicit permissions. It must never grant broad system privileges based solely on a natural-language request.

### 17.5 Multi-agent coordination

Atlas supports delegation through a coordinator.

Rules:

- Delegation creates a child task.
- The parent agent passes only the minimum required context.
- Child agents cannot inherit tools that the parent did not possess.
- Child agents cannot expand their own permissions.
- The user can inspect the task tree.
- Maximum depth is configurable and defaults to 3.
- Maximum concurrent agents is based on hardware.
- Infinite loops must be detected and stopped.
- Agent-to-agent messages are logged.

### 17.6 Task states

```text
draft
planned
awaiting_approval
queued
running
waiting_for_user
paused
completed
failed
cancelled
rolled_back
```

### 17.7 Agent execution cycle

1. Receive user request.
2. Classify task and sensitivity.
3. Select agent and workspace.
4. Retrieve relevant memory and knowledge.
5. Produce a bounded plan.
6. Policy Gateway evaluates required capabilities.
7. Obtain user approval where required.
8. Execute one state-machine step.
9. Validate tool result.
10. Update task state.
11. Repeat within limits.
12. Produce outcome, sources, actions and unresolved issues.
13. Write approved memory.
14. Finalise audit record.

### 17.8 Tool protocol

Atlas supports MCP-compatible tool servers, but all external and local tools are registered through the Atlas Tool Registry.

A tool registration contains:

- Tool identity.
- Publisher.
- Version.
- Transport.
- Input and output schemas.
- Required capabilities.
- Data classification.
- Network requirements.
- Side-effect level.
- Approval policy.
- Sandbox policy.
- Signature status.
- Health status.

Side-effect levels:

```text
0 — Read-only, no personal data
1 — Read-only, personal data
2 — Reversible local write
3 — External communication or meaningful change
4 — Destructive, financial, credential or privileged action
```

Default approvals:

- Level 0: May run automatically.
- Level 1: Allowed only within agent scope and logged.
- Level 2: User preference or per-task approval.
- Level 3: Explicit confirmation.
- Level 4: Explicit confirmation plus re-authentication; some actions remain prohibited.

### 17.9 Tool sandboxing

Tool servers must run in one of:

- Rootless container.
- systemd sandboxed service.
- Bubblewrap sandbox.
- Restricted WebAssembly runtime.
- Remote trusted endpoint.

Tools must declare:

- Filesystem paths.
- Network destinations.
- Environment secrets.
- Device access.
- Maximum CPU and RAM.
- Whether writes are reversible.

### 17.10 Prohibited default tools

No agent receives these by default:

- Unrestricted shell.
- Root shell.
- Raw Docker socket.
- Raw database administrator credentials.
- Browser credential store.
- Password vault export.
- Arbitrary USB-device access.
- Direct disk writes.
- Package-manager root access.
- Unrestricted email sending.
- Financial transaction tools.

---

## 18. Agent Memory

### 18.1 Memory types

#### Session memory

- Exists only for the active conversation or task.
- Automatically expires.

#### User memory

- Preferences and stable information approved by the user.
- Private to one user.

#### Workspace memory

- Shared facts, decisions and task history for a named workspace.

#### Agent memory

- Agent-specific operational context.
- Cannot override higher-level policy.

#### System memory

- Device configuration and health facts.
- Read-only to ordinary agents.

### 18.2 Memory consent

The interface must show:

- What will be stored.
- Which scope will store it.
- Which agents can read it.
- How long it will remain.
- How to edit or delete it.

Sensitive information must not be silently promoted from conversation context into persistent memory.

### 18.3 Memory storage

Suggested components:

- Relational database for structured memory.
- Qdrant for semantic retrieval.
- Encrypted file store for source objects.
- Per-user encryption keys protected by the OS keyring.
- Separate collections or mandatory tenant filters for users and workspaces.

### 18.4 Memory deletion

Deletion must remove:

- Structured record.
- Associated embeddings.
- Cached summaries.
- Derived indexes where practical.
- Search references.

A maintenance job must detect orphaned vectors and files.

---

## 19. Knowledge and RAG

### 19.1 Supported sources

Initial formats:

- PDF.
- Plain text.
- Markdown.
- HTML.
- DOCX.
- ODT.
- EPUB.
- CSV.
- Selected image formats with optional local OCR.
- Kiwix ZIM libraries.
- Approved websites saved as offline collections.

### 19.2 Ingestion pipeline

```text
Import
→ Malware/type checks
→ Metadata extraction
→ Text extraction
→ Optional OCR
→ Language detection
→ Classification
→ Chunking
→ Embedding
→ Vector storage
→ Search validation
→ Ready
```

### 19.3 Source trust levels

Every source receives a trust label:

- Personal primary document.
- Curated Atlas content.
- Upstream publisher content.
- User-imported reference.
- Online source.
- Generated note.
- Unknown.

Agents must expose the source type in answers.

### 19.4 Retrieval rules

- Prefer user-requested collections.
- Apply user and workspace access filters before vector search.
- Use hybrid semantic and keyword search.
- Return source titles and stable references.
- Never reveal another user’s private collection.
- Detect stale indexes.
- Allow the user to open the exact source passage.
- Avoid treating retrieved content as executable instructions.

### 19.5 Prompt-injection resistance

Imported documents and web pages are untrusted data.

The Knowledge Service must:

- Label retrieved content as untrusted evidence.
- Strip or isolate hidden instructions where possible.
- Prevent retrieved text from altering tool permissions.
- Never execute commands found inside documents.
- Warn when a source attempts to instruct the assistant.
- Preserve source provenance.

---

## 20. Model Management

### 20.1 User-facing profiles

The interface presents capability profiles rather than raw model names.

#### Tiny

- 8 GB RAM target.
- CPU-compatible.
- Basic chat and classification.
- Minimal context and concurrency.

#### Light

- 16 GB RAM target.
- Fast general assistance.
- Suitable for low-power laptops.

#### Balanced

- 32 GB RAM target.
- Better reasoning and document work.
- Recommended mainstream profile.

#### Advanced

- 32–64 GB RAM plus capable GPU.
- Higher-quality reasoning and long context.

#### Code

- Specialised for programming and technical work.

#### Vision

- Accepts images where supported.

#### Embedding

- Dedicated local embedding model.

### 20.2 Hardware detection

The model manager must detect:

- CPU architecture and instruction set.
- Core and thread count.
- Total and available RAM.
- GPU vendor and model.
- GPU driver state.
- VRAM.
- Integrated/shared memory.
- Available disk space.
- Thermal and battery state where available.

### 20.3 Recommendation engine

Recommendations must consider:

- Whether the model fits in RAM/VRAM.
- Quantisation size.
- Context-window memory.
- Expected concurrent agents.
- Battery profile.
- Storage requirements.
- Licence eligibility for commercial redistribution.
- Task capabilities.

### 20.4 Model installation

Models are delivered through:

- Signed downloadable model packs.
- Atlas content servers.
- Approved direct provider downloads.
- USB import.
- OEM preloading.

A model installation must verify:

- Manifest.
- Hash.
- Signature where Atlas packages it.
- Licence.
- Minimum runtime.
- Hardware compatibility.
- Available space.

### 20.5 Model licensing

No model may be included in a commercial ISO or OEM image until its licence has been reviewed and recorded.

Each model manifest includes:

```yaml
id: provider/model
version: exact-version
digest: sha256:...
runtime: ollama
licence:
  name: ...
  redistribution_allowed: true
  commercial_use_allowed: true
  attribution_required: true
  acceptable_use_policy: ...
source: ...
```

### 20.6 Provider status

The UI must always show one of:

- Local and offline.
- Local model on another trusted device.
- External provider enabled.
- External provider temporarily used.
- No model available.

The user must never mistake a cloud request for a local request.

---

## 21. Voice and Accessibility

### 21.1 Offline voice

Optional packs may provide:

- Local speech-to-text.
- Local text-to-speech.
- Push-to-talk.
- Wake-word disabled by default.
- Voice activity detection.
- Downloadable language packs.

### 21.2 Accessibility requirements

- Keyboard-operable interface.
- Screen-reader labels.
- High-contrast mode.
- Scalable text.
- Captions and transcripts.
- Reduced-motion mode.
- Visible focus states.
- Colour-independent status indicators.
- Dyslexia-friendly reading option.
- Simple and advanced interface modes.

### 21.3 Hearing-accessibility requirements

- Every voice response must also appear as text.
- Audio alerts must have visual equivalents.
- Setup videos must include captions.
- System notifications must not rely on sound alone.

---

## 22. Authentication and Accounts

### 22.1 Account model

Roles:

- Device owner.
- Administrator.
- Adult member.
- Child member.
- Guest.
- Organisation operator.
- Organisation member.

### 22.2 Local authentication

Supported:

- Password.
- PIN after full login.
- Optional hardware security key.
- Optional fingerprint where supported.
- Recovery codes.

### 22.3 Session rules

- Secure HTTP-only session cookies.
- CSRF protection.
- Session expiration.
- Re-authentication for sensitive actions.
- Device revocation.
- Login attempt throttling.
- No default shared administrator password.

### 22.4 Local portal access

Other devices may access Atlas only when:

- The owner explicitly enables sharing.
- The network mode permits it.
- The device authenticates.
- TLS or a secure local transport is used where practical.
- The firewall permits only the selected interface.

---

## 23. Network Modes

### 23.1 Private device mode

Default.

- Services bind to loopback.
- No LAN access.
- No incoming connections.
- Suitable for public Wi-Fi.

### 23.2 Trusted LAN mode

- Services available to approved local devices.
- Authentication required.
- Network profile marked trusted.
- Automatically disabled when network identity changes.

### 23.3 Private hotspot mode

- Atlas creates a Wi-Fi access point.
- User receives SSID and password.
- Captive-style local landing page.
- Internet forwarding optional and disabled by default.
- Connected-device list and revoke controls.

### 23.4 Offline isolation mode

- All external network egress blocked except explicitly allowed local interfaces.
- Useful for sensitive work or outages.
- UI displays a persistent isolation indicator.

### 23.5 Advanced remote mode

Not enabled in consumer defaults.

May use:

- WireGuard.
- Tailscale-style overlay.
- Organisation VPN.

Requirements:

- Explicit setup.
- Strong identity.
- No direct public port exposure.
- Audit logging.
- Clear support boundary.

---

## 24. Security Architecture

### 24.1 Threat model

Atlas must consider:

- Theft of the device.
- Malicious public networks.
- Untrusted local clients.
- Malicious documents.
- Prompt injection.
- Tool poisoning.
- Compromised container images.
- Supply-chain attacks.
- Model files with unclear provenance.
- Agent privilege escalation.
- Cross-user data leakage.
- Destructive autonomous actions.
- Failed updates.
- Malicious USB content packs.
- Browser-based attacks against local services.

### 24.2 Host security

Required defaults:

- LUKS2 encryption offered and recommended.
- Secure Boot compatibility target; custom signing may follow after version 1.
- AppArmor enabled.
- Minimal listening services.
- SSH disabled by default.
- Automatic screen lock.
- Encrypted secrets.
- Non-root everyday user.
- Sudo requires authentication.
- System daemon exposed only over Unix socket.
- Regular security updates through signed repository metadata.

### 24.3 Container security

- Pin images by digest.
- No `latest` tags in released manifests.
- Read-only root filesystem where possible.
- Drop Linux capabilities.
- Run as non-root where possible.
- No privileged containers unless documented and isolated.
- Separate networks for service groups.
- Do not publish internal databases to host interfaces.
- Health checks required.
- Resource limits required.
- Generate SBOMs.
- Scan images during CI.
- Maintain allowlist of registries.

### 24.4 Docker socket removal plan

Phase 1:

- Retain upstream compatibility inside an isolated management boundary.
- Bind UI locally.
- Add authentication in front.
- Disable shells and container actions in auxiliary tools.
- Restrict network exposure.

Phase 2:

- Introduce Atlas System Daemon.
- Move update, install and lifecycle actions to narrow APIs.
- Remove browser-facing service access to `/var/run/docker.sock`.

Phase 3:

- Run supported applications through controlled manifests and rootless execution where compatible.

### 24.5 Firewall

The firewall implementation must account for Docker-managed chains. Atlas must:

- Default-deny inbound traffic.
- Add explicit rules through supported Docker firewall integration.
- Restrict published ports to loopback unless sharing is enabled.
- Reconcile firewall state after Docker restarts.
- Unit-test network modes.
- Verify that public Wi-Fi does not expose the Command Centre.

### 24.6 Secrets

Secrets include:

- Application signing keys.
- Database passwords.
- User tokens.
- External provider API keys.
- Backup keys.
- Device identity.

Rules:

- Generate on the installed device.
- Never embed production secrets in the ISO.
- Store in root-readable files or an encrypted secret store.
- Redact from logs.
- Rotate where supported.
- Export only through explicit encrypted backup.

### 24.7 Audit log

Audit events:

- Login and logout.
- Permission change.
- Agent creation.
- Tool invocation.
- Approval and rejection.
- External network request.
- File write, move or delete by an agent.
- Backup and restore.
- Update and rollback.
- Content-pack install.
- Model install.
- Device sharing.
- Administrative change.

Audit entries must include:

- Timestamp.
- User.
- Agent.
- Task.
- Tool.
- Capability.
- Input summary.
- Result.
- Approval identity.
- Data sensitivity.
- Integrity hash.

---

## 25. Data and Storage

### 25.1 Recommended disk layout

```text
EFI System Partition       512 MiB
Root filesystem            60–100 GiB
Atlas data partition       Remaining space
Recovery partition         12–20 GiB
Swap                       ZRAM plus optional encrypted swap
```

### 25.2 Filesystem

Initial supported choices:

- Btrfs for root to support snapshots.
- Ext4 for Atlas data for broad compatibility, or Btrfs where snapshot semantics are required.
- LUKS2 beneath encrypted partitions.

### 25.3 Directory layout

```text
/srv/atlas/
├── users/
├── workspaces/
├── documents/
├── knowledge/
├── embeddings/
├── models/
├── maps/
├── kiwix/
├── kolibri/
├── media/
├── content-packs/
├── agent-packages/
├── backups/
├── exports/
├── databases/
└── logs/
```

### 25.4 Quotas

Atlas supports:

- Per-user document quota.
- Per-workspace quota.
- Model storage budget.
- Content storage budget.
- Reserved free-space threshold.
- Automatic low-space warnings.

The system must never fill the root filesystem with model or content downloads.

---

## 26. Content Pack System

### 26.1 Pack types

```text
atlas.content.knowledge
atlas.content.map
atlas.content.education
atlas.content.model
atlas.content.agent
atlas.content.workflow
atlas.content.language
atlas.content.media
```

### 26.2 Pack structure

```text
pack.atlas-pack
├── manifest.json
├── payload/
├── licences/
├── attribution/
├── migrations/
├── checksums.sha256
└── signature
```

### 26.3 Manifest fields

```json
{
  "schema": "atlas.pack/v1",
  "id": "atlas.maps.uk",
  "version": "2026.07",
  "type": "atlas.content.map",
  "name": "United Kingdom Offline Maps",
  "description": "Regional offline maps and search index.",
  "size_bytes": 0,
  "minimum_os_version": "1.0.0",
  "architectures": ["all"],
  "mount_target": "/srv/atlas/maps/uk",
  "licences": [],
  "sources": [],
  "dependencies": [],
  "conflicts": [],
  "post_install_workflow": "maps.reindex",
  "digest": "sha256:..."
}
```

### 26.4 Pack installation flow

1. Read manifest.
2. Verify schema.
3. Verify publisher signature.
4. Display licences.
5. Check compatibility.
6. Check free space.
7. Stage payload.
8. Verify individual hashes.
9. Create rollback point.
10. Install atomically.
11. Run allowlisted post-install workflow.
12. Validate health.
13. Commit or roll back.

### 26.5 Initial content packs

- Core English knowledge.
- United Kingdom maps.
- Europe maps.
- First-aid reference collection.
- Vehicle maintenance references.
- Travel planning resources.
- Family learning starter pack.
- Public-domain books.
- Technical repair references.
- Language phrase packs.

Every pack requires a redistribution audit.

---

## 27. First-Run Wizard

### 27.1 Wizard steps

#### Step 1: Welcome

Explains:

- Local-first operation.
- What remains offline.
- Optional online functions.
- Estimated setup stages.

#### Step 2: Device analysis

Displays:

- Hardware summary.
- Compatibility warnings.
- Battery health.
- Storage.
- GPU status.
- Suggested performance tier.

#### Step 3: Product profile

Select:

- Personal.
- Explorer.
- Family.
- Field.
- Private AI workstation.

#### Step 4: Privacy

Choose:

- Local only.
- Allow optional internet downloads.
- Allow optional external model provider.
- Anonymous diagnostics disabled by default.

#### Step 5: AI profile

Atlas recommends:

- Tiny.
- Light.
- Balanced.
- Advanced.
- Code.
- Vision.

Displays estimated:

- Storage.
- RAM/VRAM.
- Speed band.
- Power consumption.
- Licence.

#### Step 6: Content

Choose region and content packs.

#### Step 7: Sharing

Choose:

- This computer only.
- Trusted home network.
- Private hotspot.
- Configure later.

#### Step 8: Agents

Enable initial agents.

#### Step 9: Recovery

- Save recovery key.
- Configure backup destination.
- Create initial recovery snapshot.

#### Step 10: Provisioning

Show a clear progress timeline.

#### Step 11: Guided tour

Open the dashboard and complete a sample local query.

### 27.2 Resume behaviour

If setup is interrupted:

- Persist completed steps.
- Resume safely.
- Clean partial model/content installations.
- Never leave default credentials active.

---

## 28. Updates and Release Channels

### 28.1 Update domains

Separate channels:

- OS security packages.
- Atlas Debian packages.
- Atlas containers.
- Agent packages.
- Model metadata.
- Content packs.
- Firmware recommendations.

### 28.2 Channels

```text
stable
candidate
developer
```

Consumer systems default to `stable`.

### 28.3 Update sequence

```text
Check metadata
→ Verify signature
→ Evaluate compatibility
→ Check storage and power
→ Create snapshot
→ Download to staging
→ Verify hashes
→ Apply
→ Reboot if needed
→ Run health checks
→ Commit snapshot
```

Failure:

```text
Health check fails
→ Roll back
→ Reboot
→ Preserve diagnostics
→ Inform user
```

### 28.4 Offline updates

Users can import:

```text
atlas-update-1.0.0-to-1.1.0.bundle
```

Bundle contents:

- Signed manifest.
- Required packages.
- Required container layers.
- Migrations.
- Rollback metadata.
- Licence changes.
- Release notes.

### 28.5 Upstream update policy

Atlas does not automatically ship a new Project N.O.M.A.D. release.

Process:

1. Upstream release detected.
2. Security and feature review.
3. Rebase adapter and patches.
4. Migration test.
5. Regression test.
6. Candidate channel.
7. Stable release.

---

## 29. Backup, Restore and Recovery

### 29.1 Backup sets

#### Identity backup

- Users.
- Roles.
- Settings.
- Agent definitions.
- Secrets, encrypted.

#### Personal data backup

- Documents.
- Notes.
- Tasks.
- Workspaces.
- Agent memory.

#### Knowledge backup

- Index metadata.
- Qdrant snapshots.
- Ingestion manifests.

#### Full Atlas backup

All above plus:

- Application database.
- Content manifest.
- Model manifest.
- Network configuration.
- Audit data.

Large model and content binaries may be excluded by default because they can be reinstalled from manifests.

### 29.2 Backup targets

- External USB drive.
- External SSD.
- Trusted network share.
- Optional encrypted cloud target.
- Another Atlas device.

### 29.3 Encryption

- Backup encrypted before leaving the device.
- User chooses passphrase or recovery key.
- Atlas cannot recover forgotten user-managed keys unless a recovery arrangement is explicitly configured.

### 29.4 Factory reset modes

- Reset system settings only.
- Reset applications but preserve user data.
- Full reset and erase.
- Reinstall from recovery partition.
- Restore from backup after reset.

### 29.5 Recovery guarantees

A release is not production-ready until automated testing proves:

- Failed application update rollback.
- Failed OS update rollback.
- Restore onto a clean VM.
- Restore onto replacement compatible hardware.
- Reindex from source files when vector backup is unavailable.

---

## 30. System Health

### 30.1 Health dashboard

Displays:

- OS update status.
- Agent runtime status.
- Model runtime status.
- Knowledge index status.
- Storage.
- Memory.
- CPU/GPU load.
- Temperatures where available.
- Battery.
- Backup freshness.
- Content-pack health.
- Network mode.
- Security warnings.

### 30.2 Health severity

```text
healthy
attention
degraded
critical
```

### 30.3 Self-repair

The System Steward may invoke only predefined workflows:

- Restart a failed service.
- Rebuild a content index.
- Clear safe caches.
- Verify storage.
- Roll back an update.
- Repair permissions for known Atlas directories.
- Regenerate a non-sensitive cache.

Arbitrary command generation is prohibited.

---

## 31. Functional Requirements

### Installation

- **FR-001:** The ISO shall boot on supported x86-64 UEFI hardware.
- **FR-002:** The ISO shall provide a live environment.
- **FR-003:** The installer shall support whole-disk installation.
- **FR-004:** The installer shall offer LUKS encryption.
- **FR-005:** The installer shall create a recovery path.
- **FR-006:** The installer shall work without internet using the bundled core payload.
- **FR-007:** The installer shall generate no reusable default password.
- **FR-008:** The installer shall produce a post-install report.

### First run

- **FR-020:** Atlas shall detect CPU, RAM, storage and GPU.
- **FR-021:** Atlas shall recommend compatible model profiles.
- **FR-022:** Atlas shall estimate content and model storage.
- **FR-023:** Atlas shall resume interrupted setup.
- **FR-024:** Atlas shall generate unique device secrets.
- **FR-025:** Atlas shall create an initial rollback snapshot.

### Agents

- **FR-040:** Users shall create, edit, disable and delete custom agents.
- **FR-041:** Every agent shall have an explicit permission manifest.
- **FR-042:** Agents shall not call tools outside their allowlist.
- **FR-043:** Consequential actions shall require approval.
- **FR-044:** Users shall cancel running tasks.
- **FR-045:** Atlas shall preserve a task audit trail.
- **FR-046:** Delegated agents shall not gain additional permissions.
- **FR-047:** Agent execution shall obey step, time and tool-call limits.
- **FR-048:** Atlas shall expose source references for RAG answers.
- **FR-049:** Users shall inspect and delete agent memory.

### Models

- **FR-060:** Atlas shall support local Ollama models.
- **FR-061:** Atlas shall support optional OpenAI-compatible providers.
- **FR-062:** The UI shall distinguish local and external inference.
- **FR-063:** Atlas shall prevent installation of incompatible model packs.
- **FR-064:** Atlas shall display model licence metadata.
- **FR-065:** Atlas shall stop or queue requests when memory limits are reached.
- **FR-066:** Atlas shall support a dedicated embedding model.

### Knowledge

- **FR-080:** Users shall import supported documents.
- **FR-081:** Atlas shall show ingestion progress and errors.
- **FR-082:** Atlas shall maintain per-user and per-workspace access filters.
- **FR-083:** Atlas shall open the source passage used in an answer.
- **FR-084:** Atlas shall support reindexing.
- **FR-085:** Atlas shall snapshot and restore vector collections.
- **FR-086:** Atlas shall remove embeddings when source content is deleted.

### Content

- **FR-100:** Atlas shall install signed content packs.
- **FR-101:** Atlas shall import packs from USB.
- **FR-102:** Atlas shall verify pack checksums.
- **FR-103:** Atlas shall display licences before installation.
- **FR-104:** Atlas shall prevent root-filesystem exhaustion.
- **FR-105:** Atlas shall update packs atomically.
- **FR-106:** Atlas shall maintain an installed-content manifest.

### Network

- **FR-120:** Atlas shall default to private device mode.
- **FR-121:** Atlas shall not expose the Command Centre on public networks by default.
- **FR-122:** Atlas shall provide trusted-LAN mode.
- **FR-123:** Atlas shall provide private hotspot mode on compatible hardware.
- **FR-124:** Atlas shall list connected clients.
- **FR-125:** Atlas shall revoke a client.
- **FR-126:** Atlas shall provide offline isolation mode.

### Backup and updates

- **FR-140:** Atlas shall create encrypted backups.
- **FR-141:** Atlas shall validate backups.
- **FR-142:** Atlas shall restore selected data.
- **FR-143:** Atlas shall stage signed updates.
- **FR-144:** Atlas shall create pre-update snapshots.
- **FR-145:** Atlas shall roll back failed updates.
- **FR-146:** Atlas shall import offline update bundles.

### Administration

- **FR-160:** Atlas shall support multiple local users.
- **FR-161:** Atlas shall support role-based access.
- **FR-162:** Sensitive changes shall require re-authentication.
- **FR-163:** Atlas shall export a redacted diagnostic bundle.
- **FR-164:** Atlas shall provide an audit viewer.
- **FR-165:** Atlas shall allow the owner to disable external providers globally.

---

## 32. Non-Functional Requirements

### Performance

- **NFR-001:** Dashboard first meaningful paint within 3 seconds on recommended hardware after warm start.
- **NFR-002:** Local service health API response within 500 ms under normal load.
- **NFR-003:** Agent cancellation acknowledged within 2 seconds.
- **NFR-004:** Search results begin rendering within 2 seconds for normal local collections.
- **NFR-005:** The UI remains responsive while content is downloaded or indexed.

### Reliability

- **NFR-020:** Core services automatically restart after recoverable failure.
- **NFR-021:** Database migrations are transactional or reversible.
- **NFR-022:** A failed content install leaves the prior version usable.
- **NFR-023:** A failed system update rolls back automatically.
- **NFR-024:** Power loss during staging must not corrupt the active release.

### Security

- **NFR-040:** No production secret is embedded in the ISO.
- **NFR-041:** No database service is exposed to a LAN interface.
- **NFR-042:** Every privileged action is policy checked.
- **NFR-043:** Every agent tool call is auditable.
- **NFR-044:** External network use is visibly indicated.
- **NFR-045:** All official packs and updates are signed.
- **NFR-046:** All release containers are pinned by digest.
- **NFR-047:** User separation is enforced before retrieval, not after generation.

### Privacy

- **NFR-060:** Core use requires no Atlas cloud account.
- **NFR-061:** Telemetry is disabled by default.
- **NFR-062:** External inference is opt-in.
- **NFR-063:** The user can export and delete personal data.
- **NFR-064:** Diagnostic exports are redacted by default.

### Usability

- **NFR-080:** A normal user can complete installation without a terminal.
- **NFR-081:** Errors include a human-readable explanation and recovery action.
- **NFR-082:** Advanced technical detail is available but not required.
- **NFR-083:** Storage and performance costs are displayed before downloads.
- **NFR-084:** Destructive actions use clear, specific confirmation language.

### Accessibility

- **NFR-100:** Primary flows meet WCAG 2.2 AA where applicable.
- **NFR-101:** All audio functions have text equivalents.
- **NFR-102:** Primary flows are keyboard operable.
- **NFR-103:** The interface supports 200% scaling.

---

## 33. Hardware Support

### 33.1 Minimum supported tier

- x86-64 dual-core CPU.
- 8 GB RAM.
- 128 GB SSD.
- Integrated graphics.
- Basic non-AI or Tiny AI experience.

### 33.2 Recommended personal tier

- Modern six-core CPU.
- 16–32 GB RAM.
- 1 TB NVMe SSD.
- Integrated GPU or entry GPU.
- Light or Balanced AI profile.

### 33.3 Recommended advanced tier

- Modern eight-core CPU.
- 32–64 GB RAM.
- 2 TB NVMe SSD.
- Dedicated GPU with suitable VRAM.
- Balanced, Advanced, Code and Vision profiles.

### 33.4 OEM certification tests

Every certified device must pass:

- UEFI boot.
- Installer completion.
- Suspend and resume.
- Wi-Fi.
- Bluetooth.
- Audio input/output.
- Webcam.
- Keyboard and touchpad.
- External display.
- Battery reporting.
- Thermal load.
- Storage health.
- GPU model execution.
- Hotspot support where advertised.
- Recovery boot.
- Backup and restore smoke test.

### 33.5 Hardware compatibility database

Fields:

- Manufacturer.
- Model.
- BIOS version.
- CPU.
- GPU.
- Wi-Fi chipset.
- Storage controller.
- Tested Atlas version.
- Known issues.
- Recommended model profile.
- Hotspot support.
- Suspend status.
- Certification status.

---

## 34. Commercial Licensing and Activation

### 34.1 Core product behaviour

Locally installed core features must continue to function after purchase without requiring recurring online activation.

### 34.2 Licence options

Possible commercial enforcement:

- Signed offline licence file.
- Device-bound licence with transfer process.
- Product key converted into a signed entitlement.
- Organisation licence server for field deployments.

### 34.3 Offline activation

Process:

1. User enters licence key.
2. Atlas generates a non-sensitive device request code.
3. User activates online on another device or uses an included licence file.
4. Signed entitlement is imported.
5. Atlas verifies the entitlement offline.

### 34.4 Subscription boundaries

A subscription may cover:

- Premium update service.
- Curated content refreshes.
- Cloud backup.
- Remote support.
- Fleet management.
- Organisation catalogue.

A subscription must not disable:

- Local AI models already installed.
- Existing documents.
- Existing agents.
- Existing knowledge and maps.
- Local backup and restore.

---

## 35. Privacy and Telemetry

### 35.1 Default

No behavioural telemetry.

### 35.2 Optional diagnostics

If the user opts in, allowed diagnostic categories:

- Atlas version.
- Hardware category.
- Crash signature.
- Feature health.
- Update outcome.
- Performance band.

Never collect by default:

- Prompts.
- Responses.
- Documents.
- Embeddings.
- File names.
- Personal memory.
- Map searches.
- Exact location.
- API keys.
- Agent task contents.

### 35.3 Crash reports

Crash reports must:

- Be previewable.
- Be redacted.
- Require consent.
- Explain the destination.
- Permit saving to USB instead of uploading.

---

## 36. Application and Agent Catalogue

### 36.1 Version 1 policy

Only Atlas-reviewed applications and agents may appear in the default catalogue.

### 36.2 Publisher trust states

- Atlas signed.
- Verified partner.
- Community signed.
- Local unsigned.
- Blocked.

### 36.3 Unsigned packages

Developer mode only.

Requirements:

- Prominent warning.
- No automatic privileged capabilities.
- Separate sandbox.
- No use in child profiles.
- No silent updates.

### 36.4 Review checklist

- Licence.
- Source.
- Update mechanism.
- Network behaviour.
- Filesystem access.
- Secrets.
- Model/data provenance.
- Tool descriptions.
- Prompt-injection handling.
- Uninstall completeness.
- Resource limits.
- Security scan.

---

## 37. API Boundaries

### 37.1 Internal API groups

```text
/api/v1/auth
/api/v1/users
/api/v1/agents
/api/v1/tasks
/api/v1/tools
/api/v1/memory
/api/v1/knowledge
/api/v1/models
/api/v1/content
/api/v1/maps
/api/v1/backups
/api/v1/updates
/api/v1/system
/api/v1/audit
```

### 37.2 API rules

- Typed schemas.
- Versioned endpoints.
- Consistent error envelope.
- Correlation IDs.
- Permission check at every boundary.
- No trust based solely on frontend state.
- Sensitive fields redacted.
- Streaming task events.
- Idempotency keys for consequential operations.

### 37.3 Event bus

Example events:

```text
agent.task.created
agent.task.updated
agent.approval.required
agent.tool.started
agent.tool.completed
knowledge.ingest.progress
content.install.progress
model.download.progress
backup.completed
update.rollback
system.health.changed
network.mode.changed
```

---

## 38. Database Domains

Suggested logical domains:

```text
identity
agents
tasks
approvals
tools
memory
knowledge_metadata
content
models
backups
updates
audit
devices
settings
```

Rules:

- Database credentials isolated per service where practical.
- Schema migrations versioned.
- Backups tested.
- Personal data tagged by owner and workspace.
- Hard tenant filters in service layer.
- Audit data append-oriented.
- Retention configurable.

---

## 39. Logging and Diagnostics

### 39.1 Log levels

```text
error
warn
info
debug
trace
```

Production default: `info`.

### 39.2 Sensitive-data policy

Never log:

- Passwords.
- Tokens.
- Full prompts by default.
- Full document text.
- API keys.
- Recovery keys.
- Raw biometric data.

### 39.3 Diagnostic bundle

Contains:

- Atlas version.
- Package manifest.
- Container manifest.
- Service status.
- Redacted configuration.
- Recent errors.
- Hardware report.
- Disk report.
- Network-mode report.
- Update history.

The user previews the bundle before export.

---

## 40. Testing Strategy

### 40.1 Unit tests

Cover:

- Policy rules.
- Agent manifests.
- Approval classification.
- Model recommendations.
- Pack verification.
- Backup encryption.
- Migration logic.
- Access filters.

### 40.2 Integration tests

Cover:

- Command Centre to Agent Runtime.
- Agent Runtime to Policy Gateway.
- Policy Gateway to tool servers.
- Knowledge ingestion and retrieval.
- Model router failover.
- Content installation.
- Update staging and rollback.
- N.O.M.A.D. adapter compatibility.

### 40.3 Installer tests

Test:

- UEFI.
- Legacy BIOS where supported.
- Blank disk.
- Existing partitions.
- Encrypted installation.
- No-internet installation.
- Low-space failure.
- Interrupted installation.
- Recovery partition.
- First-run resume.

### 40.4 Virtual machine matrix

- 2 CPU / 8 GB / no GPU.
- 4 CPU / 16 GB / no GPU.
- 8 CPU / 32 GB / virtual GPU where available.
- UEFI with Secure Boot disabled.
- UEFI with target Secure Boot support.
- Different virtual disk sizes.
- Network disconnected.
- Network changes during provisioning.

### 40.5 Physical hardware matrix

At minimum:

- Intel integrated-graphics laptop.
- AMD integrated-graphics laptop.
- NVIDIA laptop.
- NVIDIA desktop.
- AMD desktop.
- Mini PC.
- USB Wi-Fi adapter.
- External SSD.
- High-DPI display.

### 40.6 Security tests

- Public-network exposure scan.
- Cross-user retrieval attempt.
- Prompt injection from document.
- Malicious MCP/tool registration.
- Agent permission escalation.
- Forged content pack.
- Forged update.
- Docker socket reachability.
- Secrets in logs.
- CSRF.
- Session fixation.
- Backup tampering.
- USB import traversal attack.
- Archive decompression bomb.
- Tool timeout and resource exhaustion.

### 40.7 Agent evaluation

Each built-in agent requires scenario tests for:

- Correct tool choice.
- Permission refusal.
- Approval request.
- Source citation.
- Memory scoping.
- Cancellation.
- Loop prevention.
- Malicious document instructions.
- Insufficient evidence.
- Offline mode.
- Low-resource model.

---

## 41. CI/CD Pipeline

```text
Commit
→ Lint
→ Unit tests
→ Dependency lock verification
→ Build Debian packages
→ Build Atlas containers
→ Build upstream-compatible NOMAD image
→ Generate SBOM
→ Scan packages and images
→ Export offline payload
→ Build ISO
→ Boot VM
→ Install VM
→ First-run test
→ Agent smoke tests
→ Network exposure test
→ Update/rollback test
→ Sign candidate
→ Publish candidate channel
→ Promote to stable after acceptance
```

Release signing keys must be held outside ordinary build containers and protected by a controlled signing process.

---

## 42. Development Phases

### Phase 0 — Legal and architectural foundation

Deliverables:

- Product name clearance.
- Upstream licence review.
- Third-party licence inventory.
- Repository structure.
- Threat model.
- Signing-key plan.
- Initial hardware targets.

Exit criteria:

- Clear commercial derivative strategy.
- No unresolved blocker around upstream redistribution.

### Phase 1 — Bootable branded OS

Deliverables:

- Debian live-build configuration.
- KDE Plasma desktop.
- Branding.
- Calamares installer.
- Encrypted install.
- First-boot marker.
- Recovery boot entry.

Exit criteria:

- ISO installs in VM without internet.
- Installed OS boots reliably.

### Phase 2 — Offline core payload

Deliverables:

- Docker installation.
- Pinned container payload.
- Project N.O.M.A.D. adapter.
- Command Centre launcher.
- Local-only bindings.
- Unique secrets.
- Health dashboard.

Exit criteria:

- Kiwix, maps and base management run after offline install.

### Phase 3 — Identity and security layer

Deliverables:

- Local accounts.
- Sessions.
- Roles.
- Reverse proxy.
- Firewall modes.
- Audit log.
- Initial System Daemon.

Exit criteria:

- No unauthenticated LAN access.
- No ordinary browser-facing root operation.

### Phase 4 — Agent runtime

Deliverables:

- Agent manifest schema.
- Task state machine.
- Model router.
- Policy Gateway.
- Tool Registry.
- Approval UI.
- Atlas Guide and Research Agent.
- Memory scopes.

Exit criteria:

- Agents complete bounded local tasks.
- Permission escalation tests fail safely.

### Phase 5 — Knowledge and documents

Deliverables:

- Import pipeline.
- Qdrant collections.
- Hybrid search.
- Source viewer.
- Document Agent.
- Backup snapshots.

Exit criteria:

- User imports documents and receives source-grounded answers.
- Cross-user leakage tests pass.

### Phase 6 — Content and models

Deliverables:

- Pack format.
- Signed catalogue.
- USB import.
- Hardware recommendations.
- Model packs.
- Storage reservations.

Exit criteria:

- Packs install and roll back atomically.
- Incompatible models are blocked.

### Phase 7 — Updates, backup and recovery

Deliverables:

- Signed APT repository.
- Application bundles.
- Offline updates.
- Btrfs snapshots.
- Recovery ISO.
- Encrypted backup and restore.

Exit criteria:

- Simulated failed update recovers automatically.
- Full restore works on clean hardware.

### Phase 8 — OEM and commercial release

Deliverables:

- OEM image.
- QC mode.
- Licence entitlement.
- User documentation.
- Support diagnostics.
- Hardware certification.
- Stable release pipeline.

Exit criteria:

- A customer can unbox a device and complete setup without technical assistance.

---

## 43. Epics and Build Order

### Epic A — Distribution builder

- Create live-build repository.
- Add package lists.
- Add branding.
- Add Calamares.
- Add installer tests.
- Produce signed ISO.

### Epic B — Atlas package suite

- Define package conventions.
- Package first-run service.
- Package shell.
- Package updater.
- Package diagnostics.
- Set up signed APT repository.

### Epic C — Offline container payload

- Pin images.
- Export OCI archive.
- Load on first boot.
- Generate secrets.
- Start services.
- Validate health.

### Epic D — Command Centre

- Navigation shell.
- Setup wizard.
- Health dashboard.
- Progress events.
- Responsive local portal.

### Epic E — Identity and permissions

- Accounts.
- Roles.
- Sessions.
- Re-authentication.
- Device clients.
- Audit.

### Epic F — Agent Runtime

- Manifests.
- Task state.
- Planner.
- Coordinator.
- Limits.
- Cancellation.
- Agent builder.

### Epic G — Policy Gateway

- Capability model.
- Tool registry.
- Approval engine.
- Audit integration.
- Sandbox adapters.
- MCP adapter.

### Epic H — Model Router

- Ollama discovery.
- Hardware probe.
- Profiles.
- Download management.
- Concurrency controls.
- Provider indicators.

### Epic I — Knowledge Service

- Import.
- Extraction.
- Chunking.
- Embedding.
- Search.
- Source viewer.
- Deletion.
- Snapshots.

### Epic J — Content system

- Pack schema.
- Signing.
- Catalogue.
- USB import.
- Atomic install.
- Licence viewer.

### Epic K — Networking

- Private mode.
- Trusted LAN.
- Hotspot.
- Isolation.
- Firewall tests.
- Client management.

### Epic L — Recovery

- Snapshots.
- Backup.
- Restore.
- Recovery ISO.
- OEM reset.
- Diagnostics.

---

## 44. Minimum Viable Technical Release

The first internal alpha must include:

- Bootable Debian-based ISO.
- Calamares installation.
- Offline installation.
- KDE Plasma desktop.
- Atlas launcher.
- Bundled pinned Project N.O.M.A.D. core.
- Kiwix.
- One regional map pack.
- Local Ollama integration.
- One suitable redistributable local chat model.
- One embedding model.
- Qdrant.
- Atlas Guide agent.
- Research Agent.
- Tool Policy Gateway.
- Local document import.
- Source-linked RAG.
- Authentication.
- Local-only networking.
- Encrypted backup.
- Snapshot rollback.
- Diagnostic bundle.

The alpha is not commercially releasable until Docker-socket exposure, update signing and recovery paths are verified.

---

## 45. Version 1 Release Criteria

Atlas OS 1.0 may ship only when:

1. The ISO installs without internet.
2. The installed system generates unique secrets.
3. Core services start automatically.
4. The Command Centre requires authentication.
5. Public-network scans show no unintended exposed services.
6. At least two local AI profiles work on certified hardware.
7. Built-in agents are bounded by explicit tool policies.
8. Document RAG returns openable sources.
9. Content packs verify signatures.
10. Model and content licences are present.
11. Update rollback passes automated tests.
12. Backup restoration passes on clean hardware.
13. Recovery media repairs or reinstalls the system.
14. The OEM image completes customer first-run setup.
15. Accessibility testing covers every primary flow.
16. The complete source and binary manifest is archived.
17. Support staff can diagnose failures from a redacted bundle.
18. Legal review confirms branding and redistribution compliance.

---

## 46. Risks and Mitigations

### Risk: Upstream changes break the Atlas fork

Mitigation:

- Pin upstream commit.
- Maintain adapters and patches separately.
- Run regression suite before rebasing.
- Avoid depending on undocumented internals.

### Risk: Docker-socket access creates host compromise

Mitigation:

- Isolate upstream component.
- Add authentication and local binding.
- Move privileged operations to Atlas System Daemon.
- Remove socket access from browser-facing services.

### Risk: Agents perform harmful actions

Mitigation:

- Capability-based permissions.
- Approval levels.
- No unrestricted shell.
- State-machine workflows.
- Sandboxed tools.
- Audit and cancellation.

### Risk: Prompt injection through downloaded content

Mitigation:

- Treat retrieved content as untrusted evidence.
- Keep policy outside prompts.
- Prevent documents from granting tools.
- Scan tool and content packages.
- Require approvals.

### Risk: Local models are too slow on customer hardware

Mitigation:

- Hardware probe.
- Conservative recommendations.
- Small default profile.
- Benchmark before installation.
- Clear expected performance.
- Optional remote provider.

### Risk: ISO becomes too large

Mitigation:

- Keep core payload small.
- Separate models and content into packs.
- Offer full OEM images for prebuilt hardware.
- Support USB side-loading.

### Risk: Content or model licence breach

Mitigation:

- Per-asset licence manifest.
- Automated release gate.
- No “download everything” commercial image.
- Legal review for curated packs.

### Risk: Supporting arbitrary hardware becomes expensive

Mitigation:

- Publish compatibility tiers.
- Certify a limited hardware range.
- Community support for unsupported devices.
- Commercial support only for certified devices.

### Risk: Failed updates brick systems

Mitigation:

- Atomic staging.
- Snapshots.
- Health checks.
- Automatic rollback.
- Recovery ISO.

### Risk: Users assume emergency or medical authority

Mitigation:

- Clear product wording.
- Source visibility.
- No diagnosis mode.
- Emergency references labelled as informational.
- Encourage professional services when available.

---

## 47. Open Decisions

These decisions must be resolved before implementation locks:

1. Final product name and trademark availability.
2. Whether Plasma remains the launch desktop or a kiosk shell becomes primary.
3. Whether Atlas reuses upstream MySQL or migrates core Atlas domains to PostgreSQL.
4. Exact local model set and redistribution rights.
5. Exact embedding model.
6. Whether Ollama runs natively or in a container on each GPU family.
7. Rootless-container compatibility for managed applications.
8. Btrfs root plus ext4 data versus Btrfs for both.
9. Secure Boot scope for version 1.
10. Commercial licence mechanism.
11. Which content packs are bundled versus downloaded.
12. Whether the first release supports multi-user Family features.
13. Whether remote access is omitted entirely from consumer 1.0.
14. Whether the Atlas Agent Runtime is entirely TypeScript or hybrid TypeScript/Python.
15. Which OCR and voice engines meet licensing and performance requirements.

---

## 48. Recommended Immediate Implementation Decisions

To prevent the project from stalling in architecture debate, use these defaults unless testing proves otherwise:

- Debian 13 Stable.
- KDE Plasma.
- Calamares.
- Btrfs root with snapshots.
- Encrypted Atlas data partition.
- Docker Engine with pinned images.
- Native Ollama where this gives the best GPU compatibility; provider adapter hides deployment differences.
- Qdrant container with snapshot support.
- TypeScript Agent Runtime with optional Python workers.
- MCP-compatible Tool Registry behind the Atlas Policy Gateway.
- React/TypeScript Command Centre.
- Local authentication from the first alpha.
- No unrestricted shell tool.
- No public internet exposure.
- Core ISO under 10 GB where achievable.
- Models and large content delivered as separate signed packs.
- Three built-in agents in alpha: Guide, Research and System Steward.
- Working product name “Atlas OS” stored only in branding configuration to permit later rename.

---

## 49. Instructions for the Build Agent

The coding agent implementing this product must follow these rules:

1. Treat this document as the product source of truth.
2. Do not silently weaken a security requirement to make a demo work.
3. Do not use floating dependency or container tags in release code.
4. Do not put secrets in the repository, ISO or logs.
5. Keep upstream Project N.O.M.A.D. source and Atlas modifications separable.
6. Build vertical slices that can be tested end to end.
7. Provide migrations for every persistent schema change.
8. Add tests with each capability.
9. Document every privileged host operation.
10. Reject arbitrary shell execution from agents.
11. Keep offline installation functional throughout development.
12. Generate machine-readable manifests for releases.
13. Make all destructive actions reversible where practical.
14. Use feature flags for incomplete modules.
15. Do not expose unfinished privileged APIs.
16. Prefer clear, maintainable components over clever abstractions.
17. Produce a working ISO at the end of every milestone.
18. Update this `product.md` when an approved architectural decision changes.

### First build assignment

The first assignment is:

> Create the `atlas-os` monorepo, implement a minimal Debian 13 `live-build` configuration, add KDE Plasma and a branded Calamares installer, package a placeholder Atlas launcher as a `.deb`, build a hybrid ISO, boot it in QEMU with UEFI, install it onto a blank virtual disk, reboot into the installed system, and provide automated scripts and test evidence for the complete path.

Acceptance evidence:

- Repository tree.
- Build command.
- ISO checksum.
- QEMU boot log.
- Installer screenshot or automated result.
- Installed-system boot log.
- Package manifest.
- Known limitations.

No AI or Project N.O.M.A.D. integration should begin until this installation foundation is reproducible.

---

## 50. Reference Baseline

The implementation should periodically revalidate these upstream assumptions because they can change.

- Project N.O.M.A.D. repository and README:  
  https://github.com/Crosstalk-Solutions/project-nomad

- Project N.O.M.A.D. FAQ and architecture notes:  
  https://github.com/Crosstalk-Solutions/project-nomad/blob/main/FAQ.md

- Project N.O.M.A.D. Apache 2.0 licence:  
  https://github.com/Crosstalk-Solutions/project-nomad/blob/main/LICENSE

- Debian live-build documentation:  
  https://manpages.debian.org/stable/live-build/live-build.7.en.html

- Calamares installer documentation:  
  https://calamares.io/docs/users-guide/

- Docker Engine on Debian and firewall behaviour:  
  https://docs.docker.com/engine/install/debian/  
  https://docs.docker.com/engine/network/packet-filtering-firewalls/

- Ollama API and OpenAI-compatible interface:  
  https://docs.ollama.com/api/introduction  
  https://docs.ollama.com/api/openai-compatibility

- Model Context Protocol specification:  
  https://modelcontextprotocol.io/specification/

- Qdrant snapshots:  
  https://qdrant.tech/documentation/snapshots/

---

## 51. Final Product Definition

Atlas OS is complete when a non-technical customer can:

1. Install it from a USB stick.
2. Encrypt the computer.
3. Select an AI profile recommended for the hardware.
4. Install useful offline knowledge and maps.
5. Import personal documents.
6. Use several private specialist agents.
7. Understand and approve agent actions.
8. Access the system safely from a trusted phone.
9. Continue using the core product without internet.
10. Update, back up, restore and recover the system without a terminal.

The product is not the ISO alone. The product is the complete, secure lifecycle:

```text
Build
→ Install
→ Configure
→ Use
→ Extend
→ Update
→ Back up
→ Recover
→ Migrate
```

That lifecycle is what turns an open-source offline server project into a supportable commercial AI operating system.
---

## 52. Authoritative Build Inputs and Asset Acquisition

### 52.1 Purpose

The build agent must not infer, browse for, or opportunistically install the components required by Atlas OS while creating a release.

All external inputs are controlled by three files:

```text
release/
├── sources.catalog.yaml
├── sources.lock.yaml
└── licences.lock.yaml
```

Responsibilities:

- `sources.catalog.yaml` describes approved upstream projects and candidate versions.
- `sources.lock.yaml` records the exact source revision, image digest, file URL, size and SHA-256 used by one Atlas release.
- `licences.lock.yaml` records the licence, attribution and redistribution decision for every bundled asset.

A production ISO build must refuse to run when:

- An input has no exact version.
- A container uses `latest` without an immutable resolved digest.
- A downloadable file has no SHA-256.
- A model has no reviewed redistribution decision.
- A required licence or attribution file is missing.
- The cache contains an object that does not match the lock file.

The acquisition pipeline and ISO build pipeline are deliberately separate:

```text
Internet-connected lock refresh
        ↓
Resolve versions and digests
        ↓
Download to immutable build cache
        ↓
Verify and licence-audit
        ↓
Commit sources.lock.yaml
        ↓
Offline ISO build from cache only
```

The ISO builder must never execute the upstream NOMAD installer.

### 52.2 What “full NOMAD” means

Project N.O.M.A.D. is not a single archive containing Wikipedia, maps, Ollama models and every optional application.

The Atlas release must acquire these layers separately:

#### Layer A — NOMAD source and management core

- Project N.O.M.A.D. source at a pinned release tag and commit.
- Upstream installation and Compose definitions for reference.
- Atlas patch set.
- Atlas-built NOMAD management image.
- MySQL.
- Redis.
- Dozzle, if included.
- NOMAD sidecar updater, only until replaced by Atlas Updater.
- NOMAD disk collector, only until replaced by Atlas System Daemon.

#### Layer B — standard NOMAD applications

- Kiwix server.
- Qdrant.
- Kolibri.
- CyberChef.
- FlatNotes.
- Ollama runtime or Atlas's compatible host-native Ollama service.
- Map renderer assets and selected PMTiles.
- Any additional Supply Depot applications explicitly approved for the edition.

#### Layer C — knowledge and model data

- Wikipedia or other Kiwix ZIM files.
- Offline regional map `.pmtiles` files.
- Kolibri channels.
- Ollama chat models.
- Ollama embedding models.
- User-selected content packs.

Atlas must package each layer independently so a release can update an application without rebuilding a 100+ GB knowledge image.

### 52.3 Initial upstream baseline

The first implementation baseline is:

```yaml
project_nomad:
  upstream_release: v1.33.0
  upstream_source_archive: >-
    https://github.com/Crosstalk-Solutions/project-nomad/archive/refs/tags/v1.33.0.tar.gz
  upstream_repository: >-
    https://github.com/Crosstalk-Solutions/project-nomad
  upstream_reference_image: >-
    ghcr.io/crosstalk-solutions/project-nomad:v1.33.0
  licence: Apache-2.0
```

The release pipeline must obtain the exact commit represented by the tag and record it in `sources.lock.yaml`.

Atlas should build its own management image from the pinned source and patch set:

```text
ghcr.io/<atlas-publisher>/atlas-nomad-core:<atlas-version>
```

The upstream image is retained as:

- A compatibility reference.
- A regression-test target.
- A fallback during early development.

It is not the final branded production image.

### 52.4 Upstream NOMAD core dependencies

The v1.33.0 management Compose baseline declares or depends on:

```yaml
core_images:
  - ghcr.io/crosstalk-solutions/project-nomad:v1.33.0
  - mysql:8.0
  - redis:7-alpine
  - amir20/dozzle:v10.0
  - ghcr.io/crosstalk-solutions/project-nomad-sidecar-updater:latest
  - ghcr.io/crosstalk-solutions/project-nomad-disk-collector:latest
```

Atlas must not preserve floating `latest` references in a release. During lock refresh, the build system resolves each image to an immutable digest:

```text
repository@sha256:<digest>
```

Example process:

```bash
skopeo inspect docker://mysql:8.0
skopeo inspect docker://redis:7-alpine
skopeo inspect docker://ghcr.io/crosstalk-solutions/project-nomad-sidecar-updater:latest
```

The resolved digest is written into `sources.lock.yaml`. The ISO build later consumes only the digest.

### 52.5 Standard application payload

The initial compatibility baseline discovered from NOMAD v1.33.x deployments is:

```yaml
standard_apps:
  kiwix:
    image: ghcr.io/kiwix/kiwix-serve:3.8.2
    purpose: Serve ZIM knowledge archives

  qdrant:
    image: qdrant/qdrant:v1.16
    purpose: Vector database for knowledge retrieval

  kolibri:
    image: treehouses/kolibri:0.12.8
    purpose: Offline education platform
    warning: >-
      This is the current NOMAD compatibility baseline, but Atlas must test
      migration to a maintained Learning Equality image before commercial release.

  cyberchef:
    image: ghcr.io/gchq/cyberchef:10.24
    purpose: Local data transformation tools

  flatnotes:
    image: dullage/flatnotes:v5.5.4
    purpose: Local Markdown notes

  ollama_container_fallback:
    image: ollama/ollama:0.24.0
    purpose: NOMAD-compatible container baseline
```

The lock-refresh job must compare these values with the pinned NOMAD source definitions. If the source declares a different version, the job must stop and request an explicit compatibility decision rather than silently choosing the newest tag.

### 52.6 Atlas Ollama decision

Atlas should use a host-native Ollama service by default rather than relying exclusively on NOMAD's Ollama container.

Reasons:

- Better Linux GPU and driver integration.
- Easier CPU, NVIDIA and AMD runtime selection.
- A single inference service can support both NOMAD and Atlas agents.
- Model files can live predictably under the Atlas data partition.
- NOMAD already supports a remote Ollama or OpenAI-compatible endpoint.

Initial runtime candidate:

```yaml
ollama:
  version: 0.31.2
  linux_amd64_archive: >-
    https://github.com/ollama/ollama/releases/download/v0.31.2/ollama-linux-amd64.tar.zst
  linux_amd64_sha256: >-
    2c88f0f31a959bac5a3cad4cc5296ec568551d4aa79f548f554adb2b575b3133
  install_target: /usr
  model_directory: /srv/atlas/models/ollama
  bind_address: 127.0.0.1:11434
  cloud_disabled: true
```

The version remains a candidate until the Atlas compatibility suite proves:

- NOMAD chat works against it.
- NOMAD model listing and pull operations work.
- Atlas Agent Runtime tool calls work.
- Embeddings work.
- CPU inference works.
- Supported NVIDIA hardware works.
- Supported AMD hardware works or cleanly falls back.
- Upgrade and rollback work.

Atlas configures:

```ini
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_MODELS=/srv/atlas/models/ollama
OLLAMA_NO_CLOUD=1
OLLAMA_MAX_LOADED_MODELS=<hardware-derived>
OLLAMA_NUM_PARALLEL=<hardware-derived>
```

NOMAD must be configured to use this endpoint through the host gateway or a narrow internal proxy.

### 52.7 Starter model payload

A model is not considered bundled merely because its Ollama tag appears in a script.

The release process must pull the model into an empty model store, package that store, hash it and save its licence.

Initial starter candidates:

```yaml
models:
  chat:
    ollama_tag: qwen3:4b
    upstream_model: Qwen/Qwen3-4B
    licence: Apache-2.0
    role: General local chat and agent tool use

  embeddings:
    ollama_tag: nomic-embed-text:v1.5
    upstream_model: nomic-ai/nomic-embed-text-v1.5
    licence: Apache-2.0
    role: NOMAD-compatible English document embeddings
```

An alternative multilingual embedding candidate is:

```yaml
ollama_tag: qwen3-embedding:0.6b
approximate_size: 639 MB
licence_review: required_before_release
```

Model-pack creation:

```bash
export OLLAMA_MODELS="$PWD/cache/ollama-models"
export OLLAMA_HOST="127.0.0.1:11434"
export OLLAMA_NO_CLOUD=1

ollama serve &
OLLAMA_PID=$!

ollama pull qwen3:4b
ollama pull nomic-embed-text:v1.5

kill "$OLLAMA_PID"
wait "$OLLAMA_PID" || true

tar --zstd -cf atlas-models-starter.tar.zst \
  -C cache ollama-models

sha256sum atlas-models-starter.tar.zst
```

The resulting tarball SHA-256, model tags, model metadata, model blob hashes, licences and Ollama version must be added to the release lock.

The customer installation must import the packaged model directory without downloading anything.

### 52.8 Wikipedia and Kiwix content

Kiwix content is distributed as ZIM files. The authoritative public download root for Wikipedia ZIMs is:

```text
https://download.kiwix.org/zim/wikipedia/
```

As of 11 July 2026, the relevant English packages are approximately:

```yaml
wikipedia_english:
  mini:
    file: wikipedia_en_all_mini_2026-06.zim
    size: 12 GB
    url: >-
      https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_mini_2026-06.zim

  no_pictures:
    file: wikipedia_en_all_nopic_2026-06.zim
    size: 49 GB
    url: >-
      https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-06.zim

  full_with_media:
    file: wikipedia_en_all_maxi_2026-02.zim
    size: 115 GB
    url: >-
      https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2026-02.zim
```

Atlas packaging policy:

- The standard installation ISO does not contain the 115 GB full Wikipedia.
- A “Starter Knowledge” ISO may include Simple English Wikipedia or another smaller curated ZIM.
- The 12 GB English mini package may be included in an expanded USB edition.
- The 49 GB no-picture package is distributed as a separate signed content pack.
- The 115 GB full package is distributed through OEM preloading, external SSD or a separate large content image.
- Build scripts must not select a file by “latest” filename matching during a production build.
- A human-approved lock refresh selects the desired dated file and records its SHA-256.

Kiwix catalog metadata may be used to discover candidates, but the release lock stores a concrete file URL and hash.

Content-pack output:

```text
atlas-wikipedia-en-mini-2026.06.atlas-pack
atlas-wikipedia-en-nopic-2026.06.atlas-pack
atlas-wikipedia-en-maxi-2026.02.atlas-pack
```

### 52.9 Maps

NOMAD's map viewer uses PMTiles and MapLibre-compatible assets.

Approved upstream discovery sources:

```yaml
nomad_map_assets:
  repository: >-
    https://github.com/Crosstalk-Solutions/project-nomad-maps
  purpose:
    - NOMAD-specific MapLibre fonts and sprites
    - Curated regional PMTiles imports

protomaps:
  project: https://protomaps.com/
  documentation: https://docs.protomaps.com/
  format: PMTiles
```

Atlas must not ship a world map by default. Planet-scale PMTiles files can exceed 100 GB.

Initial map packs:

```text
atlas-maps-uk.atlas-pack
atlas-maps-ireland.atlas-pack
atlas-maps-western-europe.atlas-pack
atlas-maps-europe.atlas-pack
```

Each pack must record:

- PMTiles source.
- Extraction boundary.
- Build date.
- OpenStreetMap attribution.
- Protomaps and PMTiles licences.
- Font and sprite licences.
- Exact hash.
- Bounding box.
- Minimum Atlas map-renderer version.

### 52.10 Kolibri content

The Kolibri application image and Kolibri learning channels are separate assets.

The ISO may contain the application without containing Khan Academy or other large education channels.

The content acquisition process must:

1. Select approved Kolibri channels.
2. Record channel IDs and versions.
3. Export channels into an offline-importable package.
4. Record the content licence for every channel.
5. Package the export as an Atlas content pack.
6. Import it during first run or OEM provisioning.

No statement such as “include Khan Academy” is sufficient for a production release. The exact channels, sizes, languages and licences must be locked.

### 52.11 OCI image acquisition

The lock-refresh machine uses `skopeo` to copy each exact container into an OCI archive without starting it:

```bash
skopeo copy \
  docker://ghcr.io/kiwix/kiwix-serve:3.8.2 \
  oci-archive:cache/oci/kiwix-serve-3.8.2.tar:kiwix-serve-3.8.2
```

For every image, record:

- Requested tag.
- Resolved multi-architecture manifest digest.
- Resolved linux/amd64 image digest.
- Source registry.
- Archive SHA-256.
- Image config digest.
- SBOM.
- Vulnerability-scan result.
- Licence decision.

The final ISO may combine approved OCI archives:

```bash
tar --zstd -cf atlas-core-oci-payload.tar.zst -C cache/oci .
sha256sum atlas-core-oci-payload.tar.zst
```

On the installed machine, first boot imports them into Docker or containerd without contacting a registry.

### 52.12 Required cache layout

```text
build-cache/
├── source/
│   ├── project-nomad-v1.33.0.tar.gz
│   └── project-nomad-v1.33.0.commit
├── deb/
├── ollama/
│   ├── ollama-linux-amd64-0.31.2.tar.zst
│   └── ollama-linux-amd64-0.31.2.sha256
├── models/
│   ├── atlas-models-starter.tar.zst
│   └── manifest.json
├── oci/
│   ├── atlas-nomad-core.tar
│   ├── mysql-8.0.tar
│   ├── redis-7-alpine.tar
│   ├── kiwix-serve-3.8.2.tar
│   ├── qdrant-v1.16.tar
│   ├── kolibri-0.12.8.tar
│   ├── cyberchef-10.24.tar
│   └── flatnotes-5.5.4.tar
├── zim/
├── maps/
├── kolibri/
├── licences/
├── sbom/
└── resolved-assets.json
```

No release build downloads directly into the live-build chroot.

### 52.13 ISO payload profiles

#### Core developer ISO

Contains:

- Debian and Atlas desktop.
- Installer.
- Atlas packages.
- NOMAD management core.
- MySQL and Redis.
- Kiwix server.
- Qdrant.
- Host-native Ollama.
- No large model or ZIM.
- Intended for engineering only.

Approximate target: 8–15 GB.

#### Standard product ISO

Contains:

- Everything in Core.
- Starter chat model.
- Starter embedding model.
- One small starter ZIM.
- UK map starter pack.
- Atlas built-in agents.

Approximate target: 15–30 GB depending on model and content choices.

#### Knowledge USB edition

Contains:

- Standard product ISO.
- English Wikipedia mini or no-picture pack.
- Additional reference ZIMs.
- Regional maps.
- Selected education channels.

Approximate target: 64–256 GB.

#### OEM full image

Contains:

- Installed Atlas OS.
- Starter and advanced model options.
- English Wikipedia package selected for the hardware SKU.
- Regional maps.
- Curated knowledge and education packs.
- Recovery partition.

Approximate target: 250 GB to multiple terabytes.

### 52.14 Lock-refresh command

The repository must expose:

```bash
make refresh-lock
```

This command:

1. Reads `sources.catalog.yaml`.
2. Resolves release tags and container digests.
3. Downloads source archives.
4. Downloads approved binaries.
5. Copies OCI images.
6. Pulls and packages approved models.
7. Optionally downloads large content.
8. Computes hashes.
9. Generates SBOMs.
10. Generates a candidate `sources.lock.yaml`.
11. Generates a licence review report.
12. Stops before promotion.

A human or authorised release process then reviews and commits the lock.

### 52.15 Offline build command

The repository must expose:

```bash
make verify-cache
make build-iso OFFLINE=1
```

`verify-cache` must compare every cached file with `sources.lock.yaml`.

`build-iso OFFLINE=1` must:

- Disable network access for the build container or VM.
- Fail if a dependency attempts a network connection.
- Install Debian packages from the cached repository snapshot.
- Embed verified Atlas packages and payloads.
- Generate the ISO.
- Prove the ISO installs while disconnected.

### 52.16 Build-agent source rule

The coding agent receives this binding instruction:

> Do not “find the latest” version of any dependency during an ISO build. Use only `sources.lock.yaml`. When an input is absent, stop and add it through the lock-refresh workflow. Never substitute a similarly named model, image, ZIM, map or channel. Never run Project N.O.M.A.D.'s network installer inside the ISO. The release ISO must be constructible from the verified build cache with the network disabled.

### 52.17 Revised first implementation assignments

#### Assignment 1 — Acquisition framework

Before building the branded ISO, create:

```text
release/sources.catalog.yaml
release/sources.lock.yaml
release/licences.lock.yaml
scripts/refresh-lock.sh
scripts/verify-cache.sh
scripts/export-oci.sh
scripts/build-model-pack.sh
```

Acceptance criteria:

- NOMAD v1.33.0 source is downloaded and hashed.
- Upstream core image is resolved to a digest.
- Core dependency images are exported to OCI archives.
- Kiwix, Qdrant and Ollama assets are cached.
- Starter-model packaging works.
- Wikipedia mini is represented in the lock, with downloading optional in CI.
- `verify-cache.sh` detects a one-byte modification.
- An offline test imports the OCI payload successfully.

#### Assignment 2 — OS foundation

Build the Debian live ISO and installer using only the verified cache.

#### Assignment 3 — NOMAD core

Install Atlas-built NOMAD management services from the bundled OCI payload.

#### Assignment 4 — AI and knowledge

Install host-native Ollama, import the starter model pack, start Qdrant, start Kiwix and register the starter ZIM.

This ordering ensures that the build agent knows exactly where every product component comes from before it begins composing the operating system.
