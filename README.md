# Unified Switch Collector

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Netmiko](https://img.shields.io/badge/netmiko-4.x-orange.svg)](https://github.com/ktbyers/netmiko)
[![Testing](https://img.shields.io/badge/pytest-153%20passed-brightgreen.svg)](https://pytest.org/)
[![Safety](https://img.shields.io/badge/credentials-sanitized-success.svg)](#security--fail-fast-safeguards)

A robust, enterprise-ready Python automation tool for auditing and collecting operational data from network switches (ArubaOS-S, HP ProCurve, Aruba 2530/2930/5400, and **ArubaOS-CX 8400**). It extracts **Serial Numbers (standalone and VSF stack members)**, **fan health**, **Power over Ethernet (PoE) remaining power**, and **member-attributed Huawei LLDP remote neighbor counts** via SSH, and consolidates everything into a single timestamped Excel workbook.

---

## Table of Contents
- [Key Features](#key-features)
- [Architecture & Workflow](#architecture--workflow)
- [Installation & Quickstart](#installation--quickstart)
- [Portable Release & Quickstart](#portable-release--quickstart)
- [Inventory Configuration](#inventory-configuration)
- [CLI Command Guide](#cli-command-guide)
- [Interactive Menu](#interactive-menu)
- [Execution Modes](#execution-modes)
- [Excel Report Specification](#excel-report-specification)
- [Multi-OS Support](#multi-os-support-arubaos-s--procurve-and-arubaos-cx)
- [Security & Fail-Fast Safeguards](#security--fail-fast-safeguards)
- [Testing](#testing)
- [Supported Platforms & Limitations](#supported-platforms--limitations)

---

## Key Features

- **Zero-Install Portable Release**: `release/Switch-Collector-v<version>-portable.zip` ships a PyInstaller-built `Switch-Collector.exe` with its runtime — operators extract and run, with no Python, pip or setup step.
- **Multi-OS Compatibility**: Collects from both ArubaOS-S / ProCurve and ArubaOS-CX (8400) fleets in one inventory, retrying each command with the other platform's syntax only when the first is rejected. Non-PoE core chassis record `Non-PoE` instead of failing.
- **Consolidated SSH Sessions**: When running in `all` mode, all commands execute over a single active SSH session per switch, preventing CPU spikes and session overhead.
- **Interactive Menu**: Run with no arguments to pick an audit type from a menu; passing `--mode` bypasses the menu entirely so automation never blocks on input.
- **Mode-Specific Reports**: Each audit writes its own named `.xlsx` containing only the columns that audit collects — a fan audit has no empty PoE or serial-number columns.
- **Single Consolidated Excel Report**: Every run produces exactly one timestamped `.xlsx` workbook with a single `Switch Data` sheet — no separate per-mode files.
- **Fan Degradation Warnings**: A member with fewer working fans than total is flagged `warning` (amber) with `Fan degraded: X/Y operational` and a remediation hint, rather than being silently reported as healthy.
- **Physical Member Unrolling**: VSF stacks are expanded into one row per physical chassis, each carrying its own Serial Number, ROM Version, fan health, and Huawei AP count.
- **Fan Health Monitoring**: Scrapes `show system fans` into an operational/total ratio (e.g. `4/4`), falling back to `Fanless` or `N/A` on fanless and unsupported platforms.
- **Member-Attributed Huawei AP Counting**: Huawei LLDP neighbours are counted per VSF member by decoding the `M/P` LocalPort prefix, so you know which chassis a Huawei access point is cabled into.
- **Diagnostic Solution Hints**: Every failed or degraded row carries a plain-language remediation hint so operators can act without reading raw logs.
- **Fail-Fast Safety**:
  - **Authentication Fail-Fast**: Exits immediately on authentication errors to prevent RADIUS/TACACS/local account lockouts.
  - **Parsing Fail-Fast**: Immediately logs syntax and structure errors without redundant SSH reconnect attempts.
- **Transient Network Retry**: Automatically retries timeout and network drops up to 3 times per device.
- **Multi-Driver Fallback**: Attempts multiple Netmiko driver types in sequence (e.g., `hp_procurve` -> `aruba_os`).
- **Sanitized Error Logging**: Automatically masks passwords with `********` if an unhandled exception or trace references credentials.

---

## Architecture & Workflow

```
+-------------------------------------------------------------+
|                      CLI Invocation                         |
|  py switch_collector.py            (interactive menu)      |
|  py switch_collector.py --mode fan (headless, no prompts)  |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                 1. Inventory Verification                   |
|  - Parse switch.txt (label | ip | username | password)      |
|  - Sanitize non-breaking spaces (\xa0)                      |
|  - Validate 4 non-empty fields (quarantine InvalidInput)    |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                 2. SSH Connection & Fallback                |
|  - Connect via Netmiko with device-type fallback            |
|  - NetmikoAuthenticationException -> STOP (1 attempt)       |
|  - NetmikoTimeoutException -> Retry up to 3x               |
|  - Single consolidated session in 'all' mode                |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                 3. Command Execution & Parsing              |
|  - ProCurve command first, ArubaOS-CX fallback on reject    |
|    sn: 'show system information'  -> 'show system'          |
|    fan: 'show system fans'         -> 'show environment fan'|
|    poe: 'show power-over-ethernet' -> 'Non-PoE' if rejected |
|    huawei-count: 'show lldp info remote-device'             |
|                -> 'show lldp neighbor-info'                 |
|  - HUAWEI entries bucketed by LocalPort M/P or M/Slot/Port  |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                 4. Member Unrolling, Hinting & Warnings     |
|  - VSF stack -> 1 row per physical chassis (Member id)      |
|  - Standalone -> 1 row (Member 1)                           |
|  - PoE remaining is a stack-level value, shared by members  |
|  - Degraded fan (X/Y) -> status 'warning' + fan hint       |
|  - Attach Solution Hint from error type + fan health        |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                 5. Excel Report Generation                  |
|  - Mode-specific name, e.g. switch_fan_audit_<ts>.xlsx      |
|  - Exactly 1 sheet: 'Switch Data'                           |
|  - Only the columns that mode collected                     |
|  - Colour-coded status column, frozen header, auto-fit      |
+-------------------------------------------------------------+
```

---

## Installation & Quickstart

1. **Clone the repository**:
   ```sh
   git clone <repo-url>
   cd Switch-Collector
   ```

2. **Set up a Python virtual environment**:
   ```sh
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```sh
   pip install -r requirements.txt
   ```

4. **Run an audit** — with no arguments you get the interactive menu:
   ```sh
   python switch_collector.py
   ```
   Or pick a mode directly for scripted/headless use:
   ```sh
   python switch_collector.py --mode all
   ```

---

## Portable Release & Quickstart

The portable release requires **zero installation**. It ships a self-contained
`Switch-Collector.exe` built with PyInstaller, so operators need **no Python, no
pip and no `setup.bat`** — just the extracted folder and a text file.

### Download

The archive is written to `release/`:

```text
release/Switch-Collector-v1.0.0-portable.zip
```

Extract it. Everything sits in a single `Switch-Collector-Portable/` folder:

```text
Switch-Collector-Portable/
  Switch-Collector.exe        <-- run this; no Python required
  _internal/                  <-- bundled interpreter + netmiko + openpyxl
  start_collector.bat         <-- double-click launcher
  switch.example.txt          <-- safe credential template
  README.md
  (setup.bat, requirements.txt, switch_collector.py are also included for
   anyone who prefers to run from source)
```

### Run It — Three Steps, No Installation

1. **Create your inventory**: copy `switch.example.txt` to `switch.txt` and fill
   in your switch IPs and credentials.
2. **Double-click `start_collector.bat`** (or run `Switch-Collector.exe`
   directly). The launcher prefers the bundled executable and only falls back
   to a system Python if the `.exe` is absent.
3. **Pick an audit** in the interactive menu, or pass a mode directly:

   ```bat
   start_collector.bat --mode all --workers 5
   ```

Reports are written to the `outputs\` folder next to the executable, and
detailed logs to `logs\` — both created on first run.

> `setup.bat` is **not required** for the portable release. It only installs
> dependencies for a source checkout.

### How the Zero-Install Launcher Decides

```text
start_collector.bat
   |
   +-- Switch-Collector.exe present?  --> run it (no Python needed)
   |
   +-- otherwise: python on PATH?     --> validate switch.txt, mkdir logs/outputs,
   |                                     run switch_collector.py
   |
   +-- neither                          --> clear error, exit 1
```

### Safe Credential Management

The release bundle ships **`switch.example.txt` only**. Your real credential
file is created locally and is guarded at three independent levels:

| Guard | Detail |
|---|---|
| Template only | `switch.txt` is never in the portable archive; only the example is. |
| Packaging blocklist | The packager treats `switch.txt` as a forbidden entry and aborts the build if it ever reaches staging or the ZIP — including inside `_internal`. |
| Git ignore | `switch.txt` is listed in `.gitignore`, so it cannot be committed by accident. |

The launcher also refuses to start when `switch.txt` is missing and tells you to
copy the template, so a half-configured install fails fast instead of producing
an empty report.

### Building the Portable Release (Maintainers)

Two steps: compile the executable, then bundle it.

```powershell
# 1. Build dist/Switch-Collector/Switch-Collector.exe + _internal/
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

# 2. Bundle it into release/Switch-Collector-v<Version>-portable.zip
powershell -ExecutionPolicy Bypass -File scripts\package_portable.ps1 -Force
```

| Parameter | Script | Meaning |
|---|---|---|
| `-Version` | `package_portable.ps1` | Release label embedded in the file name (default `1.0.0`). |
| `-Force` | `package_portable.ps1` | Replace any existing staging folder and release archive. |

`build_exe.ps1` resolves PyInstaller from a project virtualenv, the active
interpreter or `PATH`; cleans `build/` and `dist/`; runs
`pyinstaller -y switch_collector.spec`; and verifies both the executable and the
`_internal` runtime directory before reporting success.

`package_portable.ps1` **refuses to run without the compiled bundle** — a
portable release that quietly needs Python is not portable. It stages the frozen
distribution plus the six allowlisted files, runs a forbidden-entry guard over
the staged tree **and** again over the finished archive, writes the ZIP, then
removes the staging folder.

Forbidden entries — `switch.txt`, `.git`, `__pycache__`, `.pytest_cache`,
`logs`, `outputs`, `outputs_clean`, `docs`, `tests`, `*.pyc`, `*.log`, `*.xlsx`
and `*.csv` — cause the build to fail rather than ship. Inside `_internal`,
frozen bytecode (`*.pyc`) is expected, so build-artefact rules are relaxed
there; the credential rules still apply without exception.

> **Keep `_internal/` together with the `.exe`.** The two form a single unit —
> moving or renaming the executable alone will stop it from starting.

---

## Inventory Configuration

Copy the example inventory template and add your network switches:
```sh
copy switch.example.txt switch.txt   # Windows
# or: cp switch.example.txt switch.txt # Linux/macOS
```

### Format Specification
Each line must have **exactly 4 fields** separated by the pipe character (`|`):
```text
label | ip | username | password
```

### Example (`switch.txt`):
```text
SW-CORE-01 | 192.168.1.1 | admin | StrongPassword123
SW-DIST-01 | 192.168.1.2 | manager | StrongPassword123
SW-ACCESS-01 | 192.168.1.10 | operator | StrongPassword123
```

> **Security Note**: `switch.txt` is banned in `.gitignore` to prevent committing real production passwords to git. Always use `switch.example.txt` as a template.

---

## CLI Command Guide

```text
usage: switch_collector.py [-h] [--mode {sn,fan,poe,huawei-count,all}]
                           [--inventory INVENTORY] [--output-dir OUTPUT_DIR]
                           [--device-types DEVICE_TYPES]
                           [--read-timeout READ_TIMEOUT]
                           [--workers WORKERS] [--log-dir LOG_DIR]
```

### Parameter Reference
| Parameter | Required | Default | Description |
|---|---|---|---|
| `--mode` | No | interactive menu | Collection mode: `sn`, `fan`, `poe`, `huawei-count`, or `all`. Omit to use the menu. |
| `--workers` | No | `5` | Number of parallel worker threads (use `1` for sequential). |
| `--inventory` | No | `switch.txt` | Path to switch inventory file. |
| `--output-dir` | No | `outputs/` | Directory where the `.xlsx` report is saved. |
| `--log-dir` | No | `logs/` | Directory where detailed debug logs are written. |
| `--device-types` | No | `hp_procurve,aruba_os` | Comma-separated Netmiko drivers to try in order. |
| `--read-timeout` | No | `45` | SSH command read timeout in seconds. |

---

## Interactive Menu

Running the tool **without `--mode`** opens an interactive menu, which is the
easiest way to pick an audit type:

```sh
python switch_collector.py
```

```text
===================================================
               SWITCH COLLECTOR MASTER
===================================================
 [1] Full Master Audit (SN, Fan, PoE, Huawei AP)
 [2] Fan Health Audit Only
 [3] Hardware Asset Audit (Serial Number & ROM)
 [4] PoE Capacity Audit Only
 [5] Huawei AP Migration Audit Only
 [0] Exit
===================================================
Select an option [0-5]:
```

| Option | Mode | Report file |
|---|---|---|
| `1` | `all` | `switch_master_<timestamp>.xlsx` |
| `2` | `fan` | `switch_fan_audit_<timestamp>.xlsx` |
| `3` | `sn` | `switch_asset_inventory_<timestamp>.xlsx` |
| `4` | `poe` | `switch_poe_capacity_<timestamp>.xlsx` |
| `5` | `huawei-count` | `switch_huawei_ap_<timestamp>.xlsx` |
| `0` | — | Exits cleanly with `Exiting. Goodbye!` |

After choosing an audit, the tool prompts for the worker thread count:

```text
Enter number of worker threads [default 5]:
```

Press Enter to accept the default of 5. An invalid entry is rejected and
re-prompted. An invalid menu choice is likewise re-prompted rather than aborting
the run.

> **Headless automation**: passing any `--mode` skips the menu completely, so
> `python switch_collector.py --mode fan` never waits for input and is safe for
> scheduled tasks and CI. Supplying `--workers` alongside `--mode` also skips
> the worker prompt.

---

## Execution Modes

Every mode writes a single Excel report, but each produces its own file name and
its own column set — see [Excel Report Specification](#excel-report-specification).
Select a mode either from the [interactive menu](#interactive-menu) or with
`--mode`.

### 1. Serial Number Collection (`--mode sn`)
Extracts Hostname, Serial Number, and ROM Version. VSF multi-member stacks are
unrolled into one row per physical chassis.
```sh
python switch_collector.py --mode sn
```

### 2. Fan Health (`--mode fan`)
Scrapes `show system fans` and reports the operational/total fan ratio per
member. A `0 / 4` failure line becomes `4/4` (all healthy); a `1 / 4` line becomes
`3/4` (one fan failed). Fanless platforms report `Fanless`, and platforms that
expose no fan data report `N/A`.
```sh
python switch_collector.py --mode fan
```

### 3. PoE Remaining Power (`--mode poe`)
Extracts the remaining PoE power budget in Watts.
```sh
python switch_collector.py --mode poe
```

### 4. Huawei LLDP Device Count (`--mode huawei-count`)
Queries the LLDP remote neighbor table and counts connected Huawei devices,
attributed per VSF member.
```sh
python switch_collector.py --mode huawei-count
```

### 5. Consolidated Audit (`--mode all`)
Runs all four collectors (`sn`, `fan`, `poe`, `huawei-count`) over a **single
consolidated SSH connection** per switch:
```sh
python switch_collector.py --mode all
```

### Custom Inventory and Timeout Example
```sh
python switch_collector.py --mode all \
  --inventory /path/to/datacenter_switches.txt \
  --output-dir ./reports_dc/ \
  --device-types aruba_os,hp_procurve \
  --read-timeout 60
```

---

## Excel Report Specification

Each run produces **exactly one** workbook, written to the output directory
(default `outputs/`), named after the audit type:

| Mode | Filename |
|---|---|
| `all` | `switch_master_<YYYYMMDD_HHMMSS>.xlsx` |
| `fan` | `switch_fan_audit_<YYYYMMDD_HHMMSS>.xlsx` |
| `sn` | `switch_asset_inventory_<YYYYMMDD_HHMMSS>.xlsx` |
| `poe` | `switch_poe_capacity_<YYYYMMDD_HHMMSS>.xlsx` |
| `huawei-count` | `switch_huawei_ap_<YYYYMMDD_HHMMSS>.xlsx` |

The timestamp prevents overwriting a previous audit, so historical reports can
be archived side by side.

### Worksheet

The workbook contains **exactly one** worksheet named `Switch Data`. The header
row is styled dark navy (`#1F4E78`) with white bold text and is **frozen** so it
stays visible while scrolling long stacks.

### Dynamic Columns per Mode

A report only contains the columns relevant to the audit that produced it, so a
fan audit never shows empty PoE or serial-number columns:

| Mode | Columns |
|---|---|
| `all` | No, Label, IP Address, Hostname, Member, Serial Number, ROM Version, FAN, PoE Remaining (W), Huawei AP Count, Status, Error Detail, Solution Hint |
| `fan` | No, Label, IP Address, Hostname, Member, **FAN**, Status, Error Detail, Solution Hint |
| `sn` | No, Label, IP Address, Hostname, Member, **Serial Number**, **ROM Version**, Status, Error Detail, Solution Hint |
| `poe` | No, Label, IP Address, Hostname, Member, **PoE Remaining (W)**, Status, Error Detail, Solution Hint |
| `huawei-count` | No, Label, IP Address, Hostname, Member, **Huawei AP Count**, Status, Error Detail, Solution Hint |

### Physical Member Unrolling

Rows are per **physical chassis**, not per logical switch:

| Device type | Rows produced | Member values |
|---|---|---|
| Standalone switch | 1 | `1` |
| VSF stack of 3 | 3 | the real VSF member ids, e.g. `2`, `3`, `4` |
| Failed / unreadable | 1 | `1`, status `failed` |

Each member row carries its **own** Serial Number, ROM Version, `FAN` ratio, and
Huawei AP count. **PoE Remaining is a stack-level value**, so it is shared
across every member row of the same switch.

### Member-Attributed Huawei AP Counting

Huawei neighbours are bucketed by the `LocalPort` column of the LLDP table:

| LocalPort | Attributed to |
|---|---|
| `2/14` | VSF member `2` |
| `1/5` | VSF member `1` |
| `A1`, `1` (no slash) | Member `1` |

This makes it visible **which chassis** a Huawei access point is cabled into.

### Column Breakdown

| # | Column | Source | Notes |
|---|---|---|---|
| 1 | `No` | Generated | Row sequence, assigned after collection. |
| 2 | `Label` | `switch.txt` | Inventory label. |
| 3 | `IP Address` | `switch.txt` | Management IP. |
| 4 | `Hostname` | `show system information` | Falls back to the label when absent. |
| 5 | `Member` | VSF / LLDP | Physical chassis id; `1` for standalone. |
| 6 | `Serial Number` | `show system information` | Per member. `sn` / `all` only. |
| 7 | `ROM Version` | `show system information` | Per member. `sn` / `all` only. |
| 8 | `FAN` | `show system fans` | Operational/total ratio, `Fanless`, or `N/A`. `fan` / `all` only. |
| 9 | `PoE Remaining (W)` | `show power-over-ethernet` | Watts; shared across the stack. `Non-PoE` on chassis without PoE. `poe` / `all` only. |
| 10 | `Huawei AP Count` | `show lldp info remote-device` | Huawei neighbours on that member. `huawei-count` / `all` only. |
| 11 | `Status` | Derived | `success` / `warning` / `partial` / `failed` (colour-coded). |
| 12 | `Error Detail` | Netmiko / parsers / fans | Per-collector failures, collapsed to one line. |
| 13 | `Solution Hint` | Diagnostic helper | Remediation guidance. |

Columns 6–10 are omitted in single-mode runs where they were not collected.

### Status Colour Coding

| Status | Meaning | Fill | Font |
|---|---|---|---|
| `success` | Every requested collector returned data | `#C6EFCE` | `#006100` |
| `warning` | Collection succeeded, but a fan is degraded on that member | `#FFEB9C` | `#9C6500` |
| `partial` | Some collectors succeeded, others failed | `#FFEB9C` | `#9C6500` |
| `failed` | No collector succeeded | `#FFC7CE` | `#9C0006` |

A degraded fan downgrades only the affected member row to `warning`, with
`Error Detail` set to `Fan degraded: X/Y operational`. A collector failure still
outranks the fan warning, so a device that genuinely failed stays `failed`.
`Fanless` and `N/A` are healthy states, not warnings.

All column widths are auto-fitted to their content plus 4 characters of padding.

### Diagnostic Solution Hints

The `Solution Hint` column turns a raw Netmiko error into an actionable step, so
operators can triage without opening the log file:

| Trigger | Hint |
|---|---|
| `NetmikoAuthenticationException` | Verify username & password in `switch.txt`, ensure exec privilege is enabled, or check TACACS/RADIUS server. |
| `NetmikoTimeoutException` | Check ping connectivity to switch IP, verify device is powered on, and ensure port 22 is allowed by firewall/ACL. |
| `ConnectionRefusedError` | SSH service is inactive on switch. Connect via console/telnet and run `ip ssh`. |
| `ParseError` | Command output did not match expected ArubaOS format. Check firmware version or inspect raw output in logs. |
| Fan degradation (e.g. `3/4`) | Cooling fan failure on physical member. Inspect chassis fan modules in rack. |
| Partial collector failure | Some collector modules failed to return data. Check hardware feature availability or increase `read-timeout`. |

A degraded fan surfaces its hint even when every collector succeeded, because a
failing fan is a hardware fault the operator must act on regardless of the
collection status. Full raw output remains in the log file.

---

## Security & Fail-Fast Safeguards

1. **Authentication Lockout Protection**:
   Authentication errors (`NetmikoAuthenticationException`) terminate further attempts for that device immediately (`attempts = 1`). It will **never** retry incorrect passwords.
2. **Password Sanitization**:
   Whenever an exception is logged or stored, the device password is automatically masked:
   ```python
   if record["password"] and (record["password"] in err_msg):
       err_msg = err_msg.replace(record["password"], "********")
   ```
3. **Parse Fail-Fast**:
   If an unexpected response format occurs, it is recorded as a `ParseError` on that attempt count without triggering unnecessary SSH reconnects.

---

## Testing

The test suite runs 100% offline using mocked SSH sessions (`unittest.mock`), ensuring zero production switch dependencies.

Run pytest:
```sh
pytest -v
```

Coverage by area (153 tests):

| Area | Representative tests |
|---|---|
| SN parsing | `test_sn_parser_standalone_normal`, `test_sn_parser_stacked_with_blank_vsf_member` |
| PoE parsing | `test_poe_parser_normal`, `test_poe_parser_missing_power_returns_empty_string` |
| Fan parsing | `test_fan_parser_vsf_stack`, `test_fan_parser_vsf_with_failure`, `test_fan_parser_fanless` |
| Fan degradation | `test_fan_is_degraded`, `test_build_member_rows_degraded_fan_becomes_warning`, `test_build_member_rows_only_degraded_member_is_warning` |
| Huawei member attribution | `test_huawei_lldp_counter_attributed_per_member`, `test_huawei_lldp_counter_port_without_slash_is_member_one` |
| Solution hints (English) | `test_solution_hint_authentication`, `test_solution_hint_fan_failure`, `test_all_solution_hints_are_english` |
| Dynamic columns | `test_expected_column_sets_per_mode`, `test_write_excel_file_writes_only_mode_columns` |
| Report naming | `test_build_report_path_mode_specific_naming`, `test_main_writes_mode_specific_filename` |
| Excel generation | `test_write_excel_file_header_and_styling`, `test_write_excel_file_status_colours`, `test_write_excel_file_autofits_column_widths` |
| Member unrolling | `test_build_member_rows_vsf_stack_one_row_per_member`, `test_build_member_rows_sn_failure_collapses_to_single_row` |
| Retry / fail-fast | `test_collect_device_data_timeout_retry`, `test_collect_device_data_auth_fail_fast`, `test_collect_device_data_device_type_fallback_retry` |
| Interactive menu | `test_prompt_mode_maps_choices`, `test_prompt_workers_reprompts_on_invalid_input`, `test_resolve_options_headless_bypasses_menu`, `test_main_menu_exit_terminates_cleanly` |
| **ArubaOS-CX parsing** | `test_sn_parser_arubaos_cx`, `test_fan_parser_arubaos_cx_environment_fan`, `test_poe_parser_non_poe_chassis`, `test_huawei_lldp_counter_arubaos_cx_neighbor_info` |
| **Multi-OS fallbacks** | `test_collect_device_data_arubaos_cx_fallbacks`, `test_collect_device_data_procurve_sends_no_fallback`, `test_collect_device_data_cx_end_to_end_all_mode` |
| **Portable packaging** | `test_packaging_forbidden_files_excluded`, `test_start_collector_bat_exists_and_references_inventory`, `test_setup_bat_exists_and_references_requirements`, `test_package_portable_script_exists`, `test_portable_zip_contents` |
| **Standalone executable** | `test_switch_collector_spec_exists`, `test_build_exe_script_exists`, `test_start_collector_bat_prioritizes_exe`, `test_base_dir_prefers_executable_folder_when_frozen`, `test_portable_zip_contains_bundled_executable_and_internal` |
| End-to-end `main()` | `test_main_mode_all_writes_single_excel`, `test_main_vsf_stack_unrolls_member_rows`, `test_main_no_legacy_csv_outputs` |

Expected output:
```text
============================= 153 passed in 10.98s ==============================
```

---

## Multi-OS Support (ArubaOS-S / ProCurve and ArubaOS-CX)

The two switch families use different CLI syntax for the same data. Each
collector sends the ProCurve command first and automatically retries with the
ArubaOS-CX equivalent **only when the platform rejects the command or returns no
usable data**, so a working ProCurve switch never pays for an extra round-trip.

| Collector | ProCurve / ArubaOS-S | ArubaOS-CX fallback |
|---|---|---|
| `sn` | `show system information` | `show system` |
| `fan` | `show system fans` | `show environment fan` |
| `poe` | `show power-over-ethernet` | *(none — recorded as `Non-PoE`)* |
| `huawei-count` | `show lldp info remote-device` | `show lldp neighbor-info` |

### Field Label Mapping

| Logical field | ProCurve label | ArubaOS-CX label |
|---|---|---|
| Hostname | `System Name` | `Hostname` |
| Serial Number | `Serial Number` | `Chassis Serial Nbr` |
| Firmware / ROM | `ROM Version` | `ArubaOS-CX Version`, else `System Description` |

### Fan Table Differences

`show environment fan` (ArubaOS-CX) lists one row per fan with an `M/Slot/Fan`
path and a status word. The parser counts rows reporting `ok` or `ready` as
working, buckets them by member (the first digit of the path), and reports the
ratio — an 8400 chassis with 18 healthy fans reports `18/18`. Any `failed`,
`fault` or `down` fan lowers the ratio and raises the usual fan-degradation
warning.

### Non-PoE Chassis

Core chassis such as the Aruba 8400X have no PoE subsystem, so
`show power-over-ethernet` is rejected. The tool records `Non-PoE` in the
`PoE Remaining (W)` column and treats the collector as **successful** — a
missing PoE subsystem never downgrades a switch to `partial` or `failed`.

### LLDP Port Formats

`show lldp neighbor-info` (ArubaOS-CX) reports ports as `Member/Slot/Port`
(e.g. `1/1/3`), while ProCurve uses a pipe-delimited `LocalPort` of `Member/Port`
(e.g. `1/5`). Both resolve to the same member attribution, so a Huawei access
point is always credited to the physical chassis hosting its port.

---

## Supported Platforms & Limitations

- **Validated Hardware**: HP ProCurve 2530, Aruba 2530, Aruba 2930F/2930M, Aruba 5400R zl2, ArubaOS-CX 8400 (JL375A Base Chassis), VSF stacked switches.
- **Syntax Assumptions**: the ProCurve command is attempted first and the ArubaOS-CX equivalent is used as an automatic fallback — see [Multi-OS Support](#multi-os-support-arubaos-s--procurve-and-arubaos-cx).
- **Fan Reporting**: Platforms with no fans report `Fanless`; platforms exposing no fan data report `N/A`.
- **Read-Only**: The tool executes read commands only; it will never enter configuration mode (`configure terminal`).
