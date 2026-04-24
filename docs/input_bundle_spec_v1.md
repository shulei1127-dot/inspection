# Input Bundle Spec V1

## Goal

`inspection-report-platform` currently supports a small, fixed set of input
files. This document makes that support explicit so uploaded archives can be
prepared in a predictable way.

This v1 spec is intentionally narrow:

- fixed recommended directory structure
- fixed canonical file names
- fixed minimal formats
- safe fallback when some files are missing

It does **not** try to cover every Linux collection style.

## Supported Archive Formats

Current accepted upload formats:

- `.zip`
- `.tar.gz`
- `.tgz`

Platform-side compatibility exception:

- native xray `minion_report.gz`

This exception exists so the platform can accept the built-in `./minion collect`
archive name directly. The extracted content is still routed through the xray
adapter rather than the canonical input-bundle parser.

## Recommended Extracted Layout

After extraction, the archive should look like this:

```text
<bundle-root>/
  system/
    system_info
    systemctl_status
  containers/
    docker_ps
```

Recommended upload example:

```text
host-a-inspection.zip
  system/system_info
  system/systemctl_status
  containers/docker_ps
```

## Canonical File Names

The canonical v1 paths are:

- `system/system_info`
- `system/systemctl_status`
- `containers/docker_ps`

These are the names and locations new collectors should generate.

## Optional Files

All currently supported files are optional:

- `system/system_info`
- `system/systemctl_status`
- `containers/docker_ps`

If a file is missing:

- parser falls back to defaults for the related section
- `unified.json` remains valid
- warnings and issues may indicate missing host/runtime information

## File Format Requirements

### `system/system_info`

Purpose:
- populate `host_info`
- support minimal host issues

Minimal format:
- UTF-8 plain text
- one key-value pair per line
- separator must be `=` or `:`

Supported keys:
- hostname:
  - `hostname`
  - `static hostname`
- OS:
  - `pretty_name`
  - `os`
  - `os_name`
  - `name`
  - `os_version`
  - `version`
  - `version_id`
- kernel:
  - `kernel`
  - `kernel_version`
- IP:
  - `ip`
  - `ip_address`
  - `primary_ip`
- timezone:
  - `timezone`
  - `time_zone`
  - `tz`
- uptime:
  - `uptime_seconds`
  - `uptime`
- last boot:
  - `last_boot_at`
  - `last_boot_time`
  - `booted_at`

Supported uptime forms:
- integer seconds
  - `uptime_seconds=86400`
- compact duration
  - `uptime=1d 2h 3m 4s`
- word-based duration
  - `uptime=1 day 2 hours 3 minutes 4 seconds`

Supported last-boot forms:
- ISO-like timestamps
  - `last_boot_at=2026-04-10T08:30:00Z`
  - `last_boot_at=2026-04-10 16:30:00+08:00`

Example:

```text
hostname=host-a
ip=10.0.0.8
timezone=Asia/Shanghai
uptime=1 day 2 hours 3 minutes 4 seconds
last_boot_at=2026-04-10T08:30:00Z
PRETTY_NAME="Ubuntu 22.04.4 LTS"
kernel=5.15.0-105-generic
```

### `system/systemctl_status`

Purpose:
- populate `services[]`
- support minimal service issues

Minimal format:
- UTF-8 plain text
- rows similar to:
  - `systemctl list-units --type=service --all --no-pager`

Expected columns per service row:
- unit name ending in `.service`
- `LOAD`
- `ACTIVE`
- `SUB`
- optional trailing description

Example:

```text
UNIT LOAD ACTIVE SUB DESCRIPTION
nginx.service loaded active running A high performance web server
docker.service loaded active running Docker Application Container Engine
fail2ban.service loaded failed failed Fail2Ban Service
auditd.service loaded inactive dead Security Auditing Service
```

### `containers/docker_ps`

Purpose:
- populate `containers[]`
- support minimal container issues

Minimal format:
- UTF-8 plain text
- table format with header including:
  - `NAMES`
  - `IMAGE`
  - `STATUS`
- `PORTS` is optional but recommended

Recommended stable collection command:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

Recommended example:

```text
NAMES	IMAGE	STATUS	PORTS
redis	redis:7.2	Up 2 hours	0.0.0.0:6379->6379/tcp
worker	busybox:1.36	Exited (0) 3 hours ago
```

## Current Unsupported Or Unstable Cases

These are not formal v1 guarantees:

- additional log file types
- arbitrary file names outside the canonical names
- deeply custom directory layouts
- free-form JSON or YAML host metadata files
- complex `systemctl` exports that do not resemble unit rows
- highly irregular `docker ps` text without the expected header columns
- advanced host diagnostics beyond completeness and simple consistency checks

## Parser Alignment Notes

Current parser behavior is aligned to this spec in a conservative way:

- it prefers the canonical v1 paths first
- it still keeps a narrow legacy fallback to exact known file names to avoid
  breaking older local fixtures immediately

New collectors should target the canonical v1 paths only.
