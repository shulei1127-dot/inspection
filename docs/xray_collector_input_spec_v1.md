# Xray Collector Input Spec v1

## Purpose

This document defines the currently supported minimal xray input shapes supported
by `log-analyzer-service`.

The goal of v1 is narrow and practical:

- recognize one real xray collector family already seen in local samples
- recognize the built-in `./minion collect` report bundle shape
- normalize that input into the existing canonical parser inputs
- reuse the current `linux_default_parser`
- avoid introducing a broad collector framework too early

## Boundary

`xray-collector` support is analyzer-side normalization only.

The analyzer does not treat xray as a new unified JSON contract. Instead it converts
supported xray files into the existing canonical inputs:

- `system/system_info`
- `system/systemctl_status`
- `containers/docker_ps`

After normalization, the analyzer continues to produce the normal
`unified-json/v1` result.

Within the multi-product skeleton v1, this input family maps to:

- `product_type = xray`

## Supported Root Layout

v1 supports either:

1. the requested `source.path` itself being the xray root
2. one top-level child directory under `source.path` being the xray root

Typical supported layout:

```text
<source-root>/
  xray-collector.<timestamp>/
    system-logs/
      hostnamectl.txt
      timedatectl.txt
      uname.txt
      uptime.txt
      systemctl-failed.txt
    resource-snapshots/
      docker-ps-a.txt
    network/
      ip-addr.txt
```

The xray root may also be the `source.path` directly.

The adapter also supports the built-in `./minion collect` report layout:

```text
<source-root>/
  info
  config/
    mgmt_config.yml
    engine_config.yml
  logs/
    minion.log
    ...
```

This input family is normalized as `collector_type = minion-report/v1` while still
mapping to:

- `product_type = xray`
- `parser_route = xray-collector-parser`

The adapter also supports the current custom xray helper-script bundle layout:

```text
<source-root>/
  xray_log_collect_<host>_<timestamp>/
    minion_collect.txt
    docker_ps.txt
    machine_id.txt
    vuln_db_version.txt
    xray_tree.txt
    os-release.txt
    uname.txt
    uptime.txt
    date.txt
    network.txt
```

This input family is normalized as `collector_type = xray-custom-collect/v1` and
maps to:

- `product_type = xray`
- `parser_route = xray-collector-parser`

The current project-compatible helper-script layout is also supported as an
`xray-collector/v1` variant:

```text
<source-root>/
  xray-collector.<timestamp>/
    summary/
      xray_collection_summary.json
    node-info/
      versions.txt
      machine-id.txt
    health-check/
      mgmt-health.txt
      engine-health.txt
    resource-usage/
      resource-summary.txt
    resource-snapshots/
      docker-ps-a.txt
    xray-logs/
      machineid.txt
      vuln-db-version.txt
```

This variant is intended to provide machine-readable report fields first, while
still reusing the normal canonical parser path for host, service, and container
data.

## Minimal Supported Files

### Host Inputs

Preferred files:

- `system-logs/hostnamectl.txt`
- `system-logs/timedatectl.txt`
- `system-logs/uname.txt`
- `system-logs/uptime.txt`

Optional low-ambiguity boot-time file:

- `system-logs/list-boot.txt`

Optional IP files:

- `network/ip-addr.txt`
- `system-logs/ip.addr.txt`

Built-in report fallback:

- `info`
  - `Host`
  - `Docker Info`

Custom helper-script fallback:

- `minion_collect.txt`
  - `Host`
- `os-release.txt`
- `uname.txt`
- `uptime.txt`
- `date.txt`
- `network.txt`

Project-compatible helper-script source:

- `summary/xray_collection_summary.json`
  - `host.hostname`
  - `host.ip`
  - `host.os`
  - `host.kernel`
  - `host.timezone`
  - `host.uptime_seconds`
  - `host.last_boot_at`
  - `collected_at`

Current minion-report behavior:

- `hostname` comes from `Docker Info -> Name`
- `pretty_name` comes from `Docker Info -> Operating System`
- `kernel` comes from `Docker Info -> Kernel Version`
- `uptime_seconds` comes from `Host -> up time`
- `last_boot_at` comes from `Host -> boot time`
- `timezone` is reduced to a conservative UTC offset label from `Host -> host time`

### Service Inputs

Preferred xray-collector files remain:

- `minion-logs/minion-service-status.txt`
- `system-logs/systemctl-failed.txt`

Built-in report fallback sources:

- `logs/minion.log`
- `logs/wengine/supervisord.log`
- `logs/link-mgmt/supervisord.log`
- `logs/link-engine/supervisord.log`

Current minion-report behavior:

- `logs/minion.log` provides a minimal `minion` runtime signal from systemd start/stop lines
- supervisord logs provide a narrow runtime inventory for product-relevant services such as:
  - `wengine`
  - `reverse`
  - `gccd`
  - `haproxy-mgmt`
  - `openvpn-server-engine`
  - `openvpn-server-mgmt`
  - `openvpn-client`
- these entries are normalized into synthetic canonical `systemctl_status` rows
- this is intentionally a runtime inventory only and does not attempt to infer:
  - `enabled`
  - `version`
  - full host-wide service inventory

### Service Inputs

Minimal inventory source:

- `minion-logs/minion-service-status.txt`

Supported file:

- `system-logs/systemctl-failed.txt`

Current v3 behavior:

- normalize one inventory service from `minion-service-status.txt`
- merge it with failed rows from `systemctl-failed.txt`
- failed rows win on duplicate service names
- extract a minimal `enabled` value from the `Loaded:` line in `minion-service-status.txt`
  when the token is clearly `enabled` or `disabled`

This is still intentionally not a full `systemctl list-units --type=service --all`
inventory.

### Report Metadata Inputs

Project-compatible helper-script source:

- `summary/xray_collection_summary.json`
  - `versions.product_version`
  - `versions.engine_version`
  - `versions.system_version`
  - `versions.vuln_db`
  - `versions.machine_id`
  - `resources.cpu_usage_percent`
  - `resources.memory_*`
  - `resources.disk_*`
  - `containers[].container`
  - `containers[].cpu_percent`
  - `containers[].mem_percent`
- `node-info/versions.txt`
- `node-info/machine-id.txt`
- `xray-logs/machineid.txt`
- `xray-logs/vuln-db-version.txt`
- `health-check/mgmt-health.txt`
- `health-check/engine-health.txt`
- `resource-usage/resource-summary.txt`

The report date should prefer `summary.xray_collection_summary.json -> collected_at`
when available, then fall back to the platform task generation date.

Container CPU and memory percentages are mapped into optional
`containers[].cpu_percent` / `containers[].memory_percent` fields in
`unified-json/v1`, then rendered through `report_payload.container_rows[]`.

## Deployment Mode Assumption

The current xray report flow assumes `single_node` deployment by default. In this
mode, the management node and engine node are deployed on the same server, so the
engine node CPU / memory / disk fields in the report reuse the same host resource
snapshot as the management node.

Future distributed deployment support can provide explicit `xray_engine_cpu`,
`xray_engine_memory`, and `xray_engine_disk` metadata per engine node. Those
explicit values should take precedence over the single-node fallback.

### Container Inputs

Preferred file:

- `resource-snapshots/docker-ps-a.txt`

Fallback file:

- `xray-logs/container-logs/docker_ps.log`

Built-in report fallback:

- `info -> Docker Ps`

Custom helper-script fallback:

- `docker_ps.txt`

For `docker_ps.txt`, the adapter first normalizes the raw Docker CLI table into
a stable canonical shape so rows with empty `PORTS` columns do not shift the
container name or status fields.

## Optional Trend Inputs

To support the current xray trend-enhancement subchain, the preferred additional
collector artifact is:

- `resources/resource_history.csv`

Expected canonical CSV header:

```text
timestamp,cpu,memory,disk
```

Current collection recommendation:

- keep the existing current snapshot files
- additionally export recent multi-timepoint history from host-local sysstat / `sar`
- bucket to a stable 12-hour cadence
- keep empty metric cells empty instead of fabricating values

If explicit history is unavailable on the host, the bundle should still explain
that clearly through a sidecar note such as:

- `resources/resource_history_notes.txt`

This keeps the xray upload/render chain diagnosable: the platform can safely
degrade when history is absent, instead of pretending a trend exists.

## Recommended Project-Compatible Collector Layout

The current recommended script for customer-side report collection is:

- `scripts/xray_collect_report_bundle_v4_project.sh`

It intentionally writes both analyzer-compatible inputs and report-oriented
evidence directories.

Analyzer-compatible inputs:

- `system/system_info`
- `system/systemctl_status`
- `containers/docker_ps`
- `system-logs/`
- `resource-snapshots/`
- `health-checks/`
- `container-logs/`
- `minion-logs/`

Report-oriented inputs:

- `summary/xray_collection_summary.json`
- `node-info/`
- `health-check/`
- `resource-usage/`
- `container-status/`
- `container-history/`
- `anomaly-detection/`
- `minion-collect/`

This keeps the package usable by the current xray parser while giving later
adapter rounds a stable source for richer report fields such as container
restart counts, health state, exit codes, OOM evidence, and Docker daemon errors.

### Xray Metadata Inputs

Custom helper-script metadata files:

- `machine_id.txt`
  - extracts `xray_machine_id` from `Machine ID: ...`
- `vuln_db_version.txt`
  - extracts `xray_vuln_db_version` from a `hyuna-*.dump` value
- `xray_tree.txt`
  - extracts minimal management and engine installer versions from
    `x-ray-mgmt-installer-*` and `x-ray-engine-installer-*` filenames

## Mapping To Canonical Inputs

### `system/system_info`

The adapter builds `system/system_info` from the xray files above.

Current v1 field mapping:

- `hostname`:
  - preferred from `hostnamectl.txt`
  - fallback from `uname.txt`
- `pretty_name`:
  - from `hostnamectl.txt`
  - custom helper-script fallback from `os-release.txt`
- `kernel`:
  - preferred from `hostnamectl.txt`
  - fallback from `uname.txt`
- `timezone`:
  - from `timedatectl.txt`
  - custom helper-script fallback from `minion_collect.txt -> Host -> host time`
- `uptime_seconds`:
  - converted from shell-style `uptime` output
  - custom helper-script fallback from `minion_collect.txt -> Host -> up time`
- `last_boot_at`:
  - extracted from `journalctl --list-boot` output in `list-boot.txt`
  - only when boot index `0` has a clearly parseable UTC start time
  - custom helper-script fallback from `minion_collect.txt -> Host -> boot time`
- `ip`:
  - first non-loopback IPv4 address found in `ip-addr.txt` / `ip.addr.txt`
  - custom helper-script fallback from `network.txt`

### `system/systemctl_status`

The adapter now builds `system/systemctl_status` from two narrow sources:

- one running inventory row from `minion-service-status.txt`
- failed rows from `systemctl-failed.txt`

This keeps `services[]` from being failed-only while staying within a low-ambiguity
input boundary.

For the current v4 scope, the adapter may embed a minimal internal marker into the
canonical row so the existing Linux parser can recover:

- `enabled=true`
- `enabled=false`

The marker is stripped before it reaches `services[].display_name`, so downstream
report rendering still sees a clean service name/description.

### `containers/docker_ps`

The adapter strips xray collector comment preamble lines and writes a canonical
Docker table that the existing Docker parser can read.

## Minimal Format Assumptions

v1 intentionally supports a narrow set of formats:

- `hostnamectl.txt` follows normal `hostnamectl` output
- `timedatectl.txt` follows normal `timedatectl` output
- `uname.txt` contains one `uname -a` style line after optional comment lines
- `uptime.txt` contains one shell `uptime` style line after optional comment lines
- `systemctl-failed.txt` contains `systemctl --failed --no-pager` style rows
- `docker-ps-a.txt` / `docker_ps.log` contains `docker ps -a` style tabular output
- `info` follows the current built-in `./minion collect` sectioned text layout for:
  - `Host`
  - `Cpu`
  - `Memory`
  - `Disk`
  - `Minion Health`
  - `Docker Info`
  - `Docker Ps`
  - `Docker Images`

## What v1 Produces

This adapter is only expected to support the current minimum useful analyzer output:

- `host_info`
- `services`
- `containers`
- rule-based `issues`
- normal `summary`

## Out Of Scope

v1 does not support:

- archive upload directly into analyzer
- multi-collector routing framework
- every xray file under `system-logs/`, `xray-logs/`, or `container-logs/`
- deep Xray application-specific diagnosis
- AI analysis

## Relationship To Canonical Input Bundle v1

If a collector can be changed, the preferred long-term direction is still to emit the
canonical input bundle directly:

- `system/system_info`
- `system/systemctl_status`
- `containers/docker_ps`

This xray adapter exists so the analyzer can consume one real collector shape now,
without waiting for all collectors to be rewritten.

## Real Validation Notes

This v1 shape has been validated against real local samples:

- `xray-collector.20260413123039`
- `minion_report.gz`

The validation confirmed:

- `hostnamectl.txt`, `timedatectl.txt`, `uname.txt`, `uptime.txt` were normalized successfully
- `list-boot.txt` now provides a low-ambiguity `last_boot_at` when the current boot line is parseable
- `minion-service-status.txt` now provides a minimal running-service inventory row
- `minion-service-status.txt` now also provides a minimal `enabled` value when the
  `Loaded:` line is explicit enough
- `systemctl-failed.txt` produced failed-service output and service issues
- `docker-ps-a.txt` produced usable container rows for the current parser and remained
  compatible with downstream `report_payload.json` and DOCX rendering
- `info` from `minion_report.gz` now provides:
  - product version
  - engine version
  - machine id
  - mgmt/engine health summaries
  - minion RPC health summary
  - CPU / memory / root-disk summaries
  - Docker container inventory for `containers[]`
- `logs/minion.log` plus supervisord logs now lift `services[]` from `0` to a minimal
  runtime inventory for the current built-in report bundle

Follow-up limitation still observed after v2 improvements:

- standard Docker rows with empty `PORTS` are now handled more reliably, but the
  parser still targets standard table output and does not yet cover every possible
  collector-specific variation
