import pytest
import os
import re
import zipfile
from pathlib import Path
from openpyxl import load_workbook
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException, ReadTimeout
from switch_collector import (
    parse_system_information,
    parse_power_output,
    count_huawei_devices,
    parse_fan_output,
    get_solution_hint,
    get_collectors_to_run,
    get_columns_for_mode,
    build_report_path,
    build_member_rows,
    build_failed_row,
    write_excel_file,
    fan_is_degraded,
    fan_ratio,
    degraded_fan_detail,
    is_non_poe_output,
    is_invalid_command_output,
    _run_with_fallback,
    COLLECTOR_COMMANDS,
    COLLECTOR_FALLBACK_COMMANDS,
    NON_POE,
    prompt_mode,
    prompt_workers,
    resolve_runtime_options,
    MENU_OPTIONS,
    REPORT_STEMS,
    EXCEL_COLUMNS_BY_MODE,
    HINT_AUTH,
    HINT_TIMEOUT,
    HINT_CONNECTION_REFUSED,
    HINT_PARSE,
    HINT_FAN,
    HINT_PARTIAL,
    parse_inventory,
    collect_device_data,
    process_parsed_data
)

# The multi-OS command runner is private in the module; the tests exercise it
# directly, so expose it under a readable name here.
run_with_fallback = _run_with_fallback

# ==================== 1. SN PARSER TESTS ====================

def test_sn_parser_standalone_normal():
    output = """
 Status and Counters - General System Information

  System Name        : lab-sw-02
  ROM Version        : WC.16.01.0010       Serial Number      : AB12CDE3FH
  Up Time            : 84 days
"""
    results = parse_system_information(output)
    assert len(results) == 1
    assert results[0]["hostname"] == "lab-sw-02"
    assert results[0]["rom_version"] == "WC.16.01.0010"
    assert results[0]["serial_number"] == "AB12CDE3FH"

def test_sn_parser_standalone_fallback():
    output = """
 Status and Counters - General System Information

  ROM Version        : WC.16.01.0010       Serial Number      : AB12CDE3FH
  Up Time            : 84 days
"""
    results = parse_system_information(output, label="SW-FALLBACK")
    assert len(results) == 1
    assert results[0]["hostname"] == "SW-FALLBACK"
    assert results[0]["rom_version"] == "WC.16.01.0010"
    assert results[0]["serial_number"] == "AB12CDE3FH"

def test_sn_parser_stacked_normal():
    output = """
 Status and Counters - General System Information

  System Name        : lab-sw-01
  Software revision  : WC.16.11.0027

 VSF-Member :1

  ROM Version        : WC.16.01.0010
  Serial Number      : AB12CDE3FH

 VSF-Member :2

  ROM Version        : WC.16.01.0010
  Serial Number      : AB34CDE5GJ
"""
    results = parse_system_information(output)
    assert len(results) == 2
    assert results[0]["hostname"] == "lab-sw-01"
    assert results[0]["rom_version"] == "WC.16.01.0010"
    assert results[0]["serial_number"] == "AB12CDE3FH"

    assert results[1]["hostname"] == "lab-sw-01"
    assert results[1]["rom_version"] == "WC.16.01.0010"
    assert results[1]["serial_number"] == "AB34CDE5GJ"

def test_sn_parser_stacked_with_blank_vsf_member():
    output = """
 Status and Counters - General System Information

  System Name        : ASW01-HG1-L1RW

 VSF-Member :1

  ROM Version        : WC.16.01.0004
  Serial Number      : CN85K910F4

 VSF-Member :2

  ROM Version        :
  Serial Number      :

 VSF-Member :3

  ROM Version        : WC.16.01.0004
  Serial Number      : CN85K9106M
"""
    results = parse_system_information(output)
    assert len(results) == 3
    # Member 1
    assert results[0]["hostname"] == "ASW01-HG1-L1RW"
    assert results[0]["rom_version"] == "WC.16.01.0004"
    assert results[0]["serial_number"] == "CN85K910F4"
    # Member 2 (blank)
    assert results[1]["hostname"] == "ASW01-HG1-L1RW"
    assert results[1]["rom_version"] == ""
    assert results[1]["serial_number"] == ""
    # Member 3
    assert results[2]["hostname"] == "ASW01-HG1-L1RW"
    assert results[2]["rom_version"] == "WC.16.01.0004"
    assert results[2]["serial_number"] == "CN85K9106M"

def test_sn_parser_standalone_missing_fields_raises_value_error():
    output = """
 Status and Counters - General System Information

  System Name        : standalone-err
  Software revision  : WC.16.11.0027
"""
    with pytest.raises(ValueError) as exc_info:
        parse_system_information(output)
    assert "Missing ROM Version, Serial Number in standalone system information" in str(exc_info.value)


# ==================== 2. POE PARSER TESTS ====================

def test_poe_parser_normal():
    output = """
  Status and Counters - Power Over Ethernet Information

  Total PoE Power     : 720 W
  Total Remaining Power : 512 W
"""
    result = parse_power_output(output)
    assert result == "512 W"

def test_poe_parser_missing_power_returns_empty_string():
    output = """
  Status and Counters - Power Over Ethernet Information

  Total PoE Power     : 720 W
"""
    result = parse_power_output(output)
    assert result == ""


# ==================== 3. HUAWEI LLDP COUNTER TESTS ====================

def test_huawei_lldp_counter_normal():
    output = """
  LLDP Remote Devices Information

  LocalPort | ChassisId                 PortId              PortDescr
  --------- + ------------------------- ------------------- -------------------------
  1/1       | a1 b2 c3 d4 e5 f6         1/1/1               HUAWEI S5720
  1/2       | a1 b2 c3 d4 e5 f7         1/1/2               HUAWEI S5730
  1/3       | a1 b2 c3 d4 e5 f8         GigabitEthernet1/1  Cisco Catalyst
"""
    result = count_huawei_devices(output)
    # Both Huawei neighbours sit on ports 1/x, so they belong to member 1.
    assert result == {"1": 2}

def test_huawei_lldp_counter_no_huawei_returns_empty():
    output = """
  LLDP Remote Devices Information

  LocalPort | ChassisId                 PortId              PortDescr
  --------- + ------------------------- ------------------- -------------------------
  1/3       | a1 b2 c3 d4 e5 f8         GigabitEthernet1/1  Cisco Catalyst
"""
    result = count_huawei_devices(output)
    assert result == {}


def test_huawei_lldp_counter_attributed_per_member():
    """LocalPort 'M/P' maps to VSF member M; a slash-less port maps to member 1."""
    output = """
  LLDP Remote Devices Information

  LocalPort | ChassisId                 PortId              PortDescr
  --------- + ------------------------- ------------------- -------------------------
  1/1       | a1 b2 c3 d4 e5 f6         1/1/1               HUAWEI S5720
  2/14      | a1 b2 c3 d4 e5 f7         2/1/1               HUAWEI S5730
  2/15      | a1 b2 c3 d4 e5 f8         2/1/2               HUAWEI S5731
  1/2       | a1 b2 c3 d4 e5 f9         1/1/3               HUAWEI AP-8630
  1/3       | a1 b2 c3 d4 e5 fa         GigabitEthernet1/1  Cisco Catalyst
"""
    result = count_huawei_devices(output)
    assert result == {"1": 2, "2": 2}


def test_huawei_lldp_counter_port_without_slash_is_member_one():
    output = """
  LLDP Remote Devices Information

  LocalPort | ChassisId                 PortId              PortDescr
  --------- + ------------------------- ------------------- -------------------------
  A1        | a1 b2 c3 d4 e5 f6         gigabitethernet1/1  HUAWEI S5720
  1         | a1 b2 c3 d4 e5 f7         gigabitethernet1/2  HUAWEI S5720
"""
    result = count_huawei_devices(output)
    assert result == {"1": 2}


# ==================== 3b. FAN PARSER TESTS ====================

def test_fan_parser_vsf_stack():
    output = """
 Fan-Trap Status and Fan Count for VSF-Member : 2

    0 / 4 Fans in Failure State

 Fan-Trap Status and Fan Count for VSF-Member : 3

    0 / 4 Fans in Failure State

 Fan-Trap Status and Fan Count for VSF-Member : 4

    0 / 4 Fans in Failure State
"""
    result = parse_fan_output(output)
    assert result == {"2": "4/4", "3": "4/4", "4": "4/4"}


def test_fan_parser_vsf_with_failure():
    """One failed fan out of four leaves three operational fans."""
    output = """
 Fan-Trap Status and Fan Count for VSF-Member : 1

    1 / 4 Fans in Failure State
"""
    result = parse_fan_output(output)
    assert result == {"1": "3/4"}


def test_fan_parser_standalone():
    output = """
   Fan-Trap is disabled.
   0 / 2 Fans in Failure State
"""
    result = parse_fan_output(output)
    assert result == {"1": "2/2"}


def test_fan_parser_standalone_from_fan_table():
    output = """
  Fan Status

  Fan Number | State
  -----------+---------
  Fan 1      | OK
  Fan 2      | OK
"""
    result = parse_fan_output(output)
    assert result == {"1": "2/2"}


def test_fan_parser_fanless():
    result = parse_fan_output("This system does not contain any fans.")
    assert result == {"1": "Fanless"}


def test_fan_parser_no_fan_information_returns_na():
    result = parse_fan_output("unrelated CLI banner text with no relevant data")
    assert result == {"1": "N/A"}


def test_fan_parser_empty_output_returns_na():
    result = parse_fan_output("")
    assert result == {"1": "N/A"}


# ==================== 3c. SOLUTION HINT TESTS ====================

def test_solution_hint_authentication():
    hint = get_solution_hint("NetmikoAuthenticationException", "Auth failed")
    assert hint == ("Verify username & password in switch.txt, ensure exec privilege "
                    "is enabled, or check TACACS/RADIUS server.")


def test_solution_hint_timeout():
    hint = get_solution_hint("NetmikoTimeoutException", "timed out")
    assert hint == ("Check ping connectivity to switch IP, verify device is powered on, "
                    "and ensure port 22 is allowed by firewall/ACL.")


def test_solution_hint_connection_refused():
    hint = get_solution_hint("ConnectionRefusedError", "connection refused")
    assert hint == ("SSH service is inactive on switch. Connect via console/telnet "
                    "and run ip ssh.")


def test_solution_hint_parse_error():
    hint = get_solution_hint("ParseError", "Missing ROM Version")
    assert hint == ("Command output did not match expected ArubaOS format. Check "
                    "firmware version or inspect raw output in logs.")


def test_solution_hint_fan_failure():
    hint = get_solution_hint("", "", {"1": "3/4"})
    assert hint == "Cooling fan failure on physical member. Inspect chassis fan modules in rack."


def test_solution_hint_healthy_fans_returns_empty():
    assert get_solution_hint("", "", {"1": "4/4"}) == ""


def test_solution_hint_partial_collector_fail():
    hint = get_solution_hint("partial", "", {"1": "4/4"})
    assert hint == ("Some collector modules failed to return data. Check hardware "
                    "feature availability or increase read-timeout.")


def test_solution_hint_default_empty():
    assert get_solution_hint("", "", None) == ""


def test_all_solution_hints_are_english():
    """No Indonesian words may remain in the user-facing hint strings."""
    indonesian_markers = (
        "Periksa", "Cek ", "Segera", "Sebagian", "Kipas", "tidak", "aktif",
        "belum", "mengalami", "kerusakan", "di switch", "yang ", "Gagal",
    )
    for hint in (HINT_AUTH, HINT_TIMEOUT, HINT_CONNECTION_REFUSED,
                 HINT_PARSE, HINT_FAN, HINT_PARTIAL):
        for marker in indonesian_markers:
            assert marker not in hint, f"Indonesian text {marker!r} in {hint!r}"


# ==================== 3d. COLLECTOR LIST TESTS ====================

def test_get_collectors_to_run_all_includes_fan():
    assert get_collectors_to_run("all") == ["sn", "fan", "poe", "huawei-count"]


def test_get_collectors_to_run_single_mode():
    assert get_collectors_to_run("fan") == ["fan"]
    assert get_collectors_to_run("sn") == ["sn"]


def test_fan_command_is_collected_in_all_mode(monkeypatch):
    """'show system fans' must be issued when running --mode all."""
    commands = []

    class MockConnect:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def send_command(self, cmd, read_timeout):
            commands.append(cmd)
            if cmd == "show system information":
                return "System Name : test-sw\nROM Version : WC.1\nSerial Number : CN123\n"
            if cmd == "show system fans":
                return "0 / 2 Fans in Failure State\n"
            if cmd == "show power-over-ethernet":
                return "Total Remaining Power : 512 W\n"
            if cmd == "show lldp info remote-device":
                return "---+---\nHUAWEI desc\n"
            return ""

    monkeypatch.setattr("switch_collector.ConnectHandler", MockConnect)

    record = {"label": "SW1", "ip": "1.1.1.1", "username": "admin", "password": "pwd"}
    res = collect_device_data(record, ["hp_procurve"], 45, "all")

    assert "show system fans" in commands
    assert res["status"] == "success"
    assert res["attempts"]["fan"] == 1

    parsed = process_parsed_data(
        outputs=res["outputs"], label="SW1",
        collectors_to_run=["sn", "fan", "poe", "huawei-count"],
        attempts_dict=res["attempts"], errors_dict=res["errors"],
    )
    assert parsed["fan"] == {"1": "2/2"}


# ==================== 4. INVENTORY PARSER TESTS ====================

def test_inventory_parser_valid_line(tmp_path):
    p = tmp_path / "switch.txt"
    p.write_text("SW-FC-L1-2530 | 172.16.12.169 | Aruba2530 | password\n", encoding="utf-8")
    records, errors = parse_inventory(str(p))
    assert len(records) == 1
    assert len(errors) == 0
    assert records[0]["label"] == "SW-FC-L1-2530"
    assert records[0]["ip"] == "172.16.12.169"
    assert records[0]["username"] == "Aruba2530"
    assert records[0]["password"] == "password"

def test_inventory_parser_malformed_and_empty_fields(tmp_path):
    dummy_content = (
        "SW-FC-L1-2530 | 172.16.12.169 | Aruba2530\n"                     # malformed
        "SW-FC-L2-2530 |  | my_user | my_pwd\n"                             # Empty IP
        " | 172.16.12.170 | Aruba2530 | password\n"                         # Empty Label
        "SW-FC-L3-2530 | 172.16.12.171 |  | password\n"                     # Empty Username
        "SW-FC-L4-2530 | 172.16.12.172 | Aruba2530 | \n"                    # Empty Password
    )
    p = tmp_path / "test_switch_error.txt"
    p.write_text(dummy_content, encoding="utf-8")
    records, errors = parse_inventory(str(p))
    
    assert len(records) == 0
    assert len(errors) == 5
    
    # Verify generic field errors with no password leak
    for error in errors:
        msg = error["error_message"]
        assert "my_user" not in msg
        assert "my_pwd" not in msg
    
    assert errors[1]["error_message"] == "Line 2 has empty required fields: ip"
    assert errors[2]["error_message"] == "Line 3 has empty required fields: label"
    assert errors[3]["error_message"] == "Line 4 has empty required fields: username"
    assert errors[4]["error_message"] == "Line 5 has empty required fields: password"


# ==================== 5. RETRY & FAIL-FAST TESTS ====================

def test_collect_device_data_timeout_retry(monkeypatch):
    call_count = 0
    class MockConnect:
        def __init__(self, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetmikoTimeoutException("Connection timed out")
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def send_command(self, cmd, read_timeout):
            return "System Name : test-sw\nROM Version : WC.1\nSerial Number : CN123\n"
            
    monkeypatch.setattr("switch_collector.ConnectHandler", MockConnect)
    
    record = {"label": "SW1", "ip": "1.1.1.1", "username": "admin", "password": "pwd"}
    res = collect_device_data(record, ["hp_procurve"], 45, "sn")
    
    assert call_count == 2
    assert res["status"] == "success"
    assert res["attempts"]["sn"] == 2

def test_collect_device_data_auth_fail_fast(monkeypatch):
    call_count = 0
    class MockConnect:
        def __init__(self, **kwargs):
            nonlocal call_count
            call_count += 1
            raise NetmikoAuthenticationException("Auth failed")
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    monkeypatch.setattr("switch_collector.ConnectHandler", MockConnect)
    
    record = {"label": "SW1", "ip": "1.1.1.1", "username": "admin", "password": "pwd"}
    res = collect_device_data(record, ["hp_procurve", "aruba_os"], 45, "sn")
    
    # Should exit immediately on first auth error (attempts=1, no fallback to aruba_os)
    assert call_count == 1
    assert res["status"] == "failed"
    assert res["errors"]["sn"]["error_type"] == "NetmikoAuthenticationException"
    assert res["attempts"]["sn"] == 1

def test_collect_device_data_device_type_fallback_retry(monkeypatch):
    hp_procurve_calls = 0
    aruba_os_calls = 0
    
    class MockConnect:
        def __init__(self, **kwargs):
            nonlocal hp_procurve_calls, aruba_os_calls
            self.device_type = kwargs["device_type"]
            if self.device_type == "hp_procurve":
                hp_procurve_calls += 1
            elif self.device_type == "aruba_os":
                aruba_os_calls += 1
                
        def __enter__(self):
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
        def send_command(self, cmd, read_timeout):
            if self.device_type == "hp_procurve":
                if cmd == "show system information":
                    return "System Name : test-sw\nROM Version : WC.1\nSerial Number : CN123\n"
                elif cmd == "show power-over-ethernet":
                    # PoE fails with Timeout on hp_procurve
                    raise NetmikoTimeoutException("PoE Timeout on hp_procurve")
                elif cmd == "show lldp info remote-device":
                    return "---+---\nHUAWEI desc\n"
            elif self.device_type == "aruba_os":
                if cmd == "show power-over-ethernet":
                    return "Total Remaining Power : 512 W\n"
            return ""

    monkeypatch.setattr("switch_collector.ConnectHandler", MockConnect)
    
    record = {"label": "SW1", "ip": "1.1.1.1", "username": "admin", "password": "pwd"}
    res = collect_device_data(record, ["hp_procurve", "aruba_os"], 45, "all")
    
    # hp_procurve is tried 3 times (since PoE keeps failing)
    assert hp_procurve_calls == 3
    # aruba_os is tried 1 time (where PoE succeeds)
    assert aruba_os_calls == 1
    
    # Final status should be success because all three eventually succeeded!
    assert res["status"] == "success"
    # SN succeeded on the first attempt on hp_procurve
    assert res["attempts"]["sn"] == 1
    # Huawei LLDP count succeeded on the first attempt on hp_procurve
    assert res["attempts"]["huawei-count"] == 1
    # PoE succeeded on 4th attempt overall (3 on hp_procurve, 1 on aruba_os)
    assert res["attempts"]["poe"] == 4


# ==================== 6. EXCEL REPORT TESTS ====================

def _args_class(tmp_path, mode="all", workers=1):
    """Builds a fake argparse namespace pointing at tmp_path."""
    class Args:
        pass
    args = Args()
    args.mode = mode
    args.inventory = str(tmp_path / "switch.txt")
    args.output_dir = str(tmp_path / "outputs")
    args.device_types = "hp_procurve"
    args.read_timeout = 45
    args.workers = workers
    args.log_dir = str(tmp_path / "logs")
    return args


def _load_report(tmp_path, mode="all"):
    """Loads the single generated workbook and returns its data rows."""
    stem = REPORT_STEMS[mode]
    files = list((tmp_path / "outputs").glob(f"{stem}_*.xlsx"))
    assert len(files) == 1, f"expected exactly one {stem} xlsx, found {list((tmp_path / 'outputs').iterdir())}"
    return _read_workbook(files[0], mode)


def _read_workbook(path, mode="all"):
    """Reads a workbook, asserting sheet name and the mode's column set."""
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Switch Data"]

    sheet = workbook["Switch Data"]
    rows = list(sheet.iter_rows(values_only=True))
    header, data = rows[0], rows[1:]
    assert list(header) == get_columns_for_mode(mode)
    # openpyxl reads an empty cell back as None; normalise it to ''.
    records = [
        {key: ("" if value is None else value) for key, value in zip(header, row)}
        for row in data
    ]
    return sheet, records


def test_write_excel_file_header_and_styling(tmp_path):
    rows = [{
        "Label": "SW1", "IP Address": "1.1.1.1", "Member": "1", "Status": "success",
    }]
    path = tmp_path / "report.xlsx"
    write_excel_file(rows, str(path))

    assert path.exists()
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Switch Data"]
    sheet = workbook["Switch Data"]

    assert [c.value for c in sheet[1]] == get_columns_for_mode("all")
    # Header is dark navy with white bold text, frozen below row 1.
    assert sheet["A1"].fill.fgColor.rgb.endswith("1F4E78")
    assert sheet["A1"].font.bold is True
    assert sheet["A1"].font.color.rgb.endswith("FFFFFF")
    assert sheet.freeze_panes == "A2"

    # 'No' is auto-numbered from 1.
    assert sheet.cell(row=2, column=1).value == 1


@pytest.mark.parametrize("status,fill,font", [
    ("success", "C6EFCE", "006100"),
    ("warning", "FFEB9C", "9C6500"),
    ("partial", "FFEB9C", "9C6500"),
    ("failed", "FFC7CE", "9C0006"),
])
def test_write_excel_file_status_colours(tmp_path, status, fill, font):
    write_excel_file([{"Label": "SW", "Status": status}], str(tmp_path / "r.xlsx"))
    sheet = load_workbook(tmp_path / "r.xlsx")["Switch Data"]
    columns = get_columns_for_mode("all")
    status_cell = sheet.cell(row=2, column=columns.index("Status") + 1)
    assert status_cell.fill.fgColor.rgb.endswith(fill)
    assert status_cell.font.color.rgb.endswith(font)


def test_write_excel_file_autofits_column_widths(tmp_path):
    write_excel_file([{"Label": "A-very-long-switch-label", "Status": "success"}],
                     str(tmp_path / "r.xlsx"))
    sheet = load_workbook(tmp_path / "r.xlsx")["Switch Data"]
    label_width = sheet.column_dimensions["B"].width
    assert label_width >= len("A-very-long-switch-label") + 4


def test_build_member_rows_standalone_single_row():
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {
        "sn": [{"hostname": "sw1", "serial_number": "SN1", "rom_version": "WC.1"}],
        "fan": {"1": "2/2"},
        "poe": "512 W",
        "huawei-count": {"1": 3},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert len(rows) == 1
    row = rows[0]
    assert row["Member"] == "1"
    assert row["Hostname"] == "sw1"
    assert row["Serial Number"] == "SN1"
    assert row["ROM Version"] == "WC.1"
    assert row["FAN"] == "2/2"
    assert row["PoE Remaining (W)"] == "512"
    assert row["Huawei AP Count"] == 3
    assert row["Status"] == "success"


def test_build_member_rows_vsf_stack_one_row_per_member():
    """A 3-member stack produces 3 rows, each with its own SN/ROM/FAN/Huawei."""
    record = {"label": "STACK", "ip": "10.0.0.1"}
    parsed = {
        "sn": [
            {"hostname": "stack", "serial_number": "SN2", "rom_version": "WC.1"},
            {"hostname": "stack", "serial_number": "SN3", "rom_version": "WC.1"},
            {"hostname": "stack", "serial_number": "SN4", "rom_version": "WC.1"},
        ],
        "fan": {"2": "4/4", "3": "3/4", "4": "4/4"},
        "poe": "300 W",
        "huawei-count": {"2": 1, "3": 2, "4": 0},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert len(rows) == 3
    assert [r["Member"] for r in rows] == ["2", "3", "4"]
    assert [r["Serial Number"] for r in rows] == ["SN2", "SN3", "SN4"]
    assert [r["FAN"] for r in rows] == ["4/4", "3/4", "4/4"]
    assert [r["Huawei AP Count"] for r in rows] == [1, 2, 0]
    # PoE is a stack-level value, shared by every member row.
    assert all(r["PoE Remaining (W)"] == "300" for r in rows)


def test_build_member_rows_partial_status_carries_hint():
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {"sn": [{"hostname": "sw1", "serial_number": "SN1", "rom_version": "WC.1"}]}
    errors = {"poe": {"error_type": "NetmikoTimeoutException",
                      "error_message": "timed out", "attempts": 3}}

    rows = build_member_rows(record, parsed, errors, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert rows[0]["Status"] == "partial"
    assert "NetmikoTimeoutException" in rows[0]["Error Detail"]
    assert "ping" in rows[0]["Solution Hint"]


def test_build_member_rows_sn_failure_collapses_to_single_row():
    record = {"label": "SW1", "ip": "1.1.1.1"}
    errors = {"sn": {"error_type": "ParseError",
                     "error_message": "Missing ROM Version, Serial Number", "attempts": 1}}

    rows = build_member_rows(record, {}, errors, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert len(rows) == 1
    assert rows[0]["Member"] == "1"
    assert rows[0]["Status"] == "failed"
    assert "ParseError" in rows[0]["Error Detail"]
    assert "firmware" in rows[0]["Solution Hint"]


def test_build_failed_row_has_hint():
    row = build_failed_row("SWX", "9.9.9.9", "NetmikoAuthenticationException", "Auth failed")
    assert row["Member"] == "1"
    assert row["Status"] == "failed"
    assert "TACACS/RADIUS" in row["Solution Hint"]


# ==================== 7. MAIN() END-TO-END (EXCEL) TESTS ====================

def test_main_mode_all_writes_single_excel(tmp_path, monkeypatch):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "success",
            "outputs": {
                "sn": "System Name : SW1\nROM Version : WC.1\nSerial Number : CN123\n",
                "fan": "0 / 2 Fans in Failure State\n",
                "poe": "Total Remaining Power : 512 W\n",
                "huawei-count": "---+---\n1/1 | aa | 1/1/1 | HUAWEI desc\n",
            },
            "errors": {},
            "attempts": {"sn": 1, "fan": 1, "poe": 1, "huawei-count": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    _, rows = _load_report(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["No"] == 1
    assert row["Label"] == "SW1"
    assert row["IP Address"] == "1.1.1.1"
    assert row["Hostname"] == "SW1"
    assert row["Member"] == "1"
    assert row["Serial Number"] == "CN123"
    assert row["ROM Version"] == "WC.1"
    assert row["FAN"] == "2/2"
    assert row["PoE Remaining (W)"] == "512"
    assert row["Huawei AP Count"] == 1
    assert row["Status"] == "success"
    assert row["Error Detail"] == ""


def test_main_vsf_stack_unrolls_member_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("STACK | 10.0.0.1 | admin | secret\n", encoding="utf-8")

    sn_output = """
 System Name : STACK

 VSF-Member : 2
  ROM Version : WC.16.01.0010
  Serial Number : SN2

 VSF-Member : 3
  ROM Version : WC.16.01.0010
  Serial Number : SN3

 VSF-Member : 4
  ROM Version : WC.16.01.0010
  Serial Number : SN4
"""
    fan_output = """
 Fan-Trap Status and Fan Count for VSF-Member : 2
    0 / 4 Fans in Failure State

 Fan-Trap Status and Fan Count for VSF-Member : 3
    0 / 4 Fans in Failure State

 Fan-Trap Status and Fan Count for VSF-Member : 4
    1 / 4 Fans in Failure State
"""
    lldp_output = """
  LocalPort | ChassisId                 PortId   PortDescr
  --------- + ------------------------- -------- -------------------------
  2/1       | a1 b2 c3 d4 e5 f6         1/1/1    HUAWEI S5720
  3/1       | a1 b2 c3 d4 e5 f7         1/1/2    HUAWEI S5730
  4/1       | a1 b2 c3 d4 e5 f8         1/1/3    HUAWEI AP-8630
"""

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "success",
            "outputs": {
                "sn": sn_output,
                "fan": fan_output,
                "poe": "Total Remaining Power : 300 W\n",
                "huawei-count": lldp_output,
            },
            "errors": {},
            "attempts": {"sn": 1, "fan": 1, "poe": 1, "huawei-count": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    _, rows = _load_report(tmp_path)
    assert len(rows) == 3
    assert [r["Member"] for r in rows] == ["2", "3", "4"]
    assert [r["Serial Number"] for r in rows] == ["SN2", "SN3", "SN4"]
    assert [r["FAN"] for r in rows] == ["4/4", "4/4", "3/4"]
    assert [r["Huawei AP Count"] for r in rows] == [1, 1, 1]
    assert [r["No"] for r in rows] == [1, 2, 3]
    # Member 4 has a degraded fan, so only that row is downgraded to warning.
    assert [r["Status"] for r in rows] == ["success", "success", "warning"]
    assert rows[2]["Error Detail"] == "Fan degraded: 3/4 operational"
    assert rows[2]["Solution Hint"] == HINT_FAN
    # Healthy members carry no fan detail or hint.
    assert rows[0]["Error Detail"] == ""
    assert rows[0]["Solution Hint"] == ""
    # PoE is shared across the stack.
    assert all(r["PoE Remaining (W)"] == "300" for r in rows)


def test_main_partial_status_written_to_excel(tmp_path, monkeypatch):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "partial",
            "outputs": {
                "sn": "System Name : SW1\nROM Version : WC.1\nSerial Number : CN123\n",
                "huawei-count": "---+---\nHUAWEI desc\n",
            },
            "errors": {
                "fan": {"error_type": "NetmikoTimeoutException",
                        "error_message": "Connection timed out", "attempts": 3},
                "poe": {"error_type": "NetmikoTimeoutException",
                        "error_message": "Connection timed out", "attempts": 3},
            },
            "attempts": {"sn": 1, "fan": 3, "poe": 3, "huawei-count": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    _, rows = _load_report(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["Status"] == "partial"
    assert row["Serial Number"] == "CN123"
    assert "poe" in row["Error Detail"] and "fan" in row["Error Detail"]
    assert "ping" in row["Solution Hint"]


def test_main_fully_failed_device_single_row(tmp_path, monkeypatch):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "failed",
            "outputs": {},
            "errors": {
                "sn": {"error_type": "NetmikoTimeoutException", "error_message": "SN timeout", "attempts": 3},
                "fan": {"error_type": "NetmikoTimeoutException", "error_message": "Fan timeout", "attempts": 3},
                "poe": {"error_type": "NetmikoTimeoutException", "error_message": "PoE timeout", "attempts": 3},
                "huawei-count": {"error_type": "ReadTimeout", "error_message": "Huawei timeout", "attempts": 3},
            },
            "attempts": {"sn": 3, "fan": 3, "poe": 3, "huawei-count": 3},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    sheet, rows = _load_report(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["Label"] == "SW1"
    assert row["Member"] == "1"
    assert row["Status"] == "failed"
    assert row["Error Detail"]
    assert "ping" in row["Solution Hint"]

    # Failed rows are colour-coded red.
    columns = get_columns_for_mode("all")
    status_cell = sheet.cell(row=2, column=columns.index("Status") + 1)
    assert status_cell.fill.fgColor.rgb.endswith("FFC7CE")


def test_main_no_legacy_csv_outputs(tmp_path, monkeypatch):
    """Phase 8 consolidates everything into one workbook; CSVs are gone."""
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "success",
            "outputs": {
                "sn": "System Name : SW1\nROM Version : WC.1\nSerial Number : CN123\n",
                "fan": "0 / 2 Fans in Failure State\n",
                "poe": "Total Remaining Power : 512 W\n",
                "huawei-count": "---+---\nHUAWEI desc\n",
            },
            "errors": {},
            "attempts": {"sn": 1, "fan": 1, "poe": 1, "huawei-count": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    produced = sorted(p.name for p in (tmp_path / "outputs").iterdir())
    assert len(produced) == 1, produced
    assert produced[0].endswith(".xlsx")
    assert not list((tmp_path / "outputs").glob("*.csv"))


def test_main_invalid_inventory_line_becomes_failed_row(tmp_path, monkeypatch):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW-BAD | 1.1.1.1 | admin\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        raise AssertionError("should not be called for a malformed line")

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    _, rows = _load_report(tmp_path)
    assert len(rows) == 1
    assert rows[0]["Status"] == "failed"
    assert "InvalidInput" in rows[0]["Error Detail"]


def test_main_parallel_workers_produces_same_excel(tmp_path, monkeypatch):
    """workers > 1 must aggregate results into the same single workbook."""
    monkeypatch.setattr("switch_collector.parse_args",
                        lambda: _args_class(tmp_path, workers=4))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text(
        "SW1 | 1.1.1.1 | admin | secret\n"
        "SW2 | 1.1.1.2 | admin | secret\n"
        "SW3 | 1.1.1.3 | admin | secret\n",
        encoding="utf-8",
    )

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "success",
            "outputs": {
                "sn": "System Name : {}\nROM Version : WC.1\nSerial Number : SN{}\n".format(
                    record["label"], record["label"]),
                "fan": "0 / 2 Fans in Failure State\n",
                "poe": "Total Remaining Power : 512 W\n",
                "huawei-count": "---+---\nHUAWEI desc\n",
            },
            "errors": {},
            "attempts": {"sn": 1, "fan": 1, "poe": 1, "huawei-count": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    _, rows = _load_report(tmp_path)
    assert len(rows) == 3
    assert sorted(r["Label"] for r in rows) == ["SW1", "SW2", "SW3"]
    # 'No' is assigned deterministically after collection, so it is 1..3.
    assert sorted(r["No"] for r in rows) == [1, 2, 3]
    assert all(r["Status"] == "success" for r in rows)


# ==================== 8. FAN DEGRADATION WARNING ====================

def test_fan_ratio_parses_operational_total():
    assert fan_ratio("3/4") == (3, 4)
    assert fan_ratio(" 1 / 2 ") == (1, 2)
    assert fan_ratio("Fanless") is None
    assert fan_ratio("N/A") is None
    assert fan_ratio("") is None


@pytest.mark.parametrize("value,degraded", [
    ("4/4", False),
    ("2/2", False),
    ("3/4", True),
    ("1/2", True),
    ("0/1", True),
    ("Fanless", False),
    ("N/A", False),
])
def test_fan_is_degraded(value, degraded):
    assert fan_is_degraded(value) is degraded


def test_fan_is_degraded_on_dict_finds_any_member():
    assert fan_is_degraded({"1": "4/4", "2": "3/4"}) is True
    assert fan_is_degraded({"1": "4/4", "2": "4/4"}) is False


def test_degraded_fan_detail_names_member():
    detail = degraded_fan_detail({"1": "4/4", "2": "3/4", "3": "1/2"})
    assert "3/4" in detail
    assert "1/2" in detail
    assert degraded_fan_detail({"1": "4/4"}) == ""


def test_build_member_rows_degraded_fan_becomes_warning():
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {
        "sn": [{"hostname": "sw1", "serial_number": "SN1", "rom_version": "WC.1"}],
        "fan": {"1": "3/4"},
        "poe": "512 W",
        "huawei-count": {"1": 1},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert rows[0]["Status"] == "warning"
    assert rows[0]["Error Detail"] == "Fan degraded: 3/4 operational"
    assert rows[0]["Solution Hint"] == HINT_FAN
    assert rows[0]["FAN"] == "3/4"


def test_build_member_rows_healthy_fan_stays_success():
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {
        "sn": [{"hostname": "sw1", "serial_number": "SN1", "rom_version": "WC.1"}],
        "fan": {"1": "4/4"},
        "poe": "512 W",
        "huawei-count": {"1": 1},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert rows[0]["Status"] == "success"
    assert rows[0]["Error Detail"] == ""
    assert rows[0]["Solution Hint"] == ""


def test_build_member_rows_sn_collapse_beats_fan_warning():
    """An unreadable SN list collapses to a failed row, ignoring fan state."""
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {"fan": {"1": "1/2"}}
    errors = {"sn": {"error_type": "NetmikoTimeoutException",
                     "error_message": "timed out", "attempts": 3},
              "poe": {"error_type": "NetmikoTimeoutException",
                      "error_message": "timed out", "attempts": 3},
              "huawei-count": {"error_type": "NetmikoTimeoutException",
                               "error_message": "timed out", "attempts": 3}}

    rows = build_member_rows(record, parsed, errors, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert len(rows) == 1
    assert rows[0]["Status"] == "failed"
    # The collector failure hint wins over the fan hint.
    assert rows[0]["Solution Hint"] == HINT_TIMEOUT


def test_build_member_rows_partial_status_stays_partial():
    """Fan degradation must not mask a partial collection."""
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {
        "sn": [{"hostname": "sw1", "serial_number": "SN1", "rom_version": "WC.1"}],
        "fan": {"1": "3/4"},
    }
    errors = {"poe": {"error_type": "NetmikoTimeoutException",
                      "error_message": "timed out", "attempts": 3}}

    rows = build_member_rows(record, parsed, errors, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert rows[0]["Status"] == "partial"


def test_build_member_rows_fanless_is_not_a_warning():
    record = {"label": "SW1", "ip": "1.1.1.1"}
    parsed = {
        "sn": [{"hostname": "sw1", "serial_number": "SN1", "rom_version": "WC.1"}],
        "fan": {"1": "Fanless"},
        "poe": "512 W",
        "huawei-count": {"1": 1},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])
    assert rows[0]["Status"] == "success"


def test_build_member_rows_only_degraded_member_is_warning():
    """A healthy member in a stack with one failed fan stays 'success'."""
    record = {"label": "STACK", "ip": "10.0.0.1"}
    parsed = {
        "sn": [{"hostname": "stack", "serial_number": "SN1", "rom_version": "WC.1"},
               {"hostname": "stack", "serial_number": "SN2", "rom_version": "WC.1"},
               {"hostname": "stack", "serial_number": "SN3", "rom_version": "WC.1"}],
        "fan": {"1": "4/4", "2": "4/4", "3": "2/4"},
        "poe": "300 W",
        "huawei-count": {"1": 0, "2": 0, "3": 0},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert [r["Status"] for r in rows] == ["success", "success", "warning"]
    assert rows[2]["Error Detail"] == "Fan degraded: 2/4 operational"
    assert rows[0]["Error Detail"] == ""


# ==================== 9. DYNAMIC COLUMNS PER MODE ====================

def test_expected_column_sets_per_mode():
    assert get_columns_for_mode("all") == [
        "No", "Label", "IP Address", "Hostname", "Member", "Serial Number",
        "ROM Version", "FAN", "PoE Remaining (W)", "Huawei AP Count",
        "Status", "Error Detail", "Solution Hint",
    ]
    assert get_columns_for_mode("fan") == [
        "No", "Label", "IP Address", "Hostname", "Member", "FAN",
        "Status", "Error Detail", "Solution Hint",
    ]
    assert get_columns_for_mode("sn") == [
        "No", "Label", "IP Address", "Hostname", "Member",
        "Serial Number", "ROM Version", "Status", "Error Detail", "Solution Hint",
    ]
    assert get_columns_for_mode("poe") == [
        "No", "Label", "IP Address", "Hostname", "Member",
        "PoE Remaining (W)", "Status", "Error Detail", "Solution Hint",
    ]
    assert get_columns_for_mode("huawei-count") == [
        "No", "Label", "IP Address", "Hostname", "Member",
        "Huawei AP Count", "Status", "Error Detail", "Solution Hint",
    ]


@pytest.mark.parametrize("mode", ["all", "fan", "sn", "poe", "huawei-count"])
def test_write_excel_file_writes_only_mode_columns(tmp_path, mode):
    path = tmp_path / f"{mode}.xlsx"
    write_excel_file([{"Label": "SW1", "Status": "success"}], str(path), mode=mode)

    sheet = load_workbook(path)["Switch Data"]
    header = [c.value for c in sheet[1]]
    expected = get_columns_for_mode(mode)

    assert header == expected
    # No duplicates, and nothing beyond the mode's own column set.
    assert len(header) == len(set(header))
    assert set(header) == set(expected)
    # A single-mode report is strictly narrower than the full master report.
    if mode != "all":
        assert set(header) < set(get_columns_for_mode("all"))


def test_write_excel_file_fan_mode_omits_irrelevant_columns(tmp_path):
    path = tmp_path / "fan.xlsx"
    write_excel_file([{"Label": "SW1", "FAN": "4/4", "Status": "success"}],
                     str(path), mode="fan")
    header = [c.value for c in load_workbook(path)["Switch Data"][1]]

    assert "FAN" in header
    for absent in ("Serial Number", "ROM Version", "PoE Remaining (W)", "Huawei AP Count"):
        assert absent not in header


def test_write_excel_file_accepts_explicit_columns(tmp_path):
    path = tmp_path / "custom.xlsx"
    write_excel_file([{"Label": "SW1", "Status": "success"}], str(path),
                     columns=["Label", "Status"])
    header = [c.value for c in load_workbook(path)["Switch Data"][1]]
    assert header == ["Label", "Status"]


def test_get_columns_for_mode_unknown_falls_back_to_full_set():
    assert get_columns_for_mode("nope") == EXCEL_COLUMNS_BY_MODE["all"]


# ==================== 10. MODE-SPECIFIC FILE NAMING ====================

@pytest.mark.parametrize("mode,stem", [
    ("all", "switch_master"),
    ("fan", "switch_fan_audit"),
    ("sn", "switch_asset_inventory"),
    ("poe", "switch_poe_capacity"),
    ("huawei-count", "switch_huawei_ap"),
])
def test_build_report_path_mode_specific_naming(mode, stem):
    path = build_report_path("outputs", mode, "20260928_093000")
    assert path == os.path.join("outputs", f"{stem}_20260928_093000.xlsx")
    assert REPORT_STEMS[mode] == stem


def test_build_report_path_keeps_directory_separator():
    path = build_report_path("C:\\tmp\\out", "fan", "20260928_093000")
    assert path.startswith("C:\\tmp\\out")
    assert path.endswith("switch_fan_audit_20260928_093000.xlsx")


@pytest.mark.parametrize("mode,stem", [
    ("all", "switch_master"),
    ("fan", "switch_fan_audit"),
    ("sn", "switch_asset_inventory"),
    ("poe", "switch_poe_capacity"),
    ("huawei-count", "switch_huawei_ap"),
])
def test_main_writes_mode_specific_filename(tmp_path, monkeypatch, mode, stem):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path, mode=mode, workers=1))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, m, logger):
        outputs = {}
        attempts = {}
        if m == "sn" or m == "all":
            outputs["sn"] = "System Name : SW1\nROM Version : WC.1\nSerial Number : CN123\n"
            attempts["sn"] = 1
        if m == "fan" or m == "all":
            outputs["fan"] = "0 / 2 Fans in Failure State\n"
            attempts["fan"] = 1
        if m == "poe" or m == "all":
            outputs["poe"] = "Total Remaining Power : 512 W\n"
            attempts["poe"] = 1
        if m == "huawei-count" or m == "all":
            outputs["huawei-count"] = "---+---\n1/1 | aa | 1/1/1 | HUAWEI desc\n"
            attempts["huawei-count"] = 1
        return {"status": "success", "outputs": outputs, "errors": {}, "attempts": attempts}

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    files = list((tmp_path / "outputs").glob("*.xlsx"))
    assert len(files) == 1, files
    assert files[0].name.startswith(f"{stem}_")
    assert files[0].name.endswith(".xlsx")
    # The sheet carries only this mode's columns.
    _read_workbook(files[0], mode)


def test_main_fan_mode_report_has_no_empty_data_columns(tmp_path, monkeypatch):
    """A --mode fan run must not emit SN/PoE/Huawei columns at all."""
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path, mode="fan", workers=1))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "success",
            "outputs": {"fan": "1 / 2 Fans in Failure State\n"},
            "errors": {},
            "attempts": {"fan": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    _, rows = _load_report(tmp_path, mode="fan")
    assert len(rows) == 1
    assert rows[0]["FAN"] == "1/2"
    assert rows[0]["Status"] == "warning"
    assert "Serial Number" not in rows[0]


def test_main_degraded_fan_written_as_warning_row(tmp_path, monkeypatch):
    monkeypatch.setattr("switch_collector.parse_args", lambda: _args_class(tmp_path, mode="fan", workers=1))
    monkeypatch.setattr("os.path.dirname", lambda path: str(tmp_path))
    (tmp_path / "switch.txt").write_text("SW1 | 1.1.1.1 | admin | secret\n", encoding="utf-8")

    def mock_collect(record, device_types, read_timeout, mode, logger):
        return {
            "status": "success",
            "outputs": {"fan": "1 / 2 Fans in Failure State\n"},
            "errors": {},
            "attempts": {"fan": 1},
        }

    monkeypatch.setattr("switch_collector.collect_device_data", mock_collect)

    import switch_collector
    switch_collector.main()

    sheet, rows = _load_report(tmp_path, mode="fan")
    assert rows[0]["Status"] == "warning"
    assert rows[0]["Error Detail"] == "Fan degraded: 1/2 operational"
    assert rows[0]["Solution Hint"] == HINT_FAN

    # Warning rows are shaded light yellow with dark yellow text.
    columns = get_columns_for_mode("fan")
    status_cell = sheet.cell(row=2, column=columns.index("Status") + 1)
    assert status_cell.fill.fgColor.rgb.endswith("FFEB9C")
    assert status_cell.font.color.rgb.endswith("9C6500")


# ==================== 11. INTERACTIVE MENU ====================

def _menu_input(answers):
    """Returns an input_fn that walks the given answers, then raises."""
    it = iter(answers)
    return lambda prompt="": next(it)


@pytest.mark.parametrize("choice,mode", [
    ("1", "all"),
    ("2", "fan"),
    ("3", "sn"),
    ("4", "poe"),
    ("5", "huawei-count"),
])
def test_prompt_mode_maps_choices(choice, mode):
    assert prompt_mode(input_fn=_menu_input([choice]), print_fn=lambda *a, **k: None) == mode


def test_prompt_mode_exit_returns_none():
    assert prompt_mode(input_fn=_menu_input(["0"]), print_fn=lambda *a, **k: None) is None


def test_prompt_mode_reprompts_on_invalid_choice():
    assert prompt_mode(input_fn=_menu_input(["9", "x", "2"]),
                       print_fn=lambda *a, **k: None) == "fan"


def test_prompt_workers_defaults_on_empty_input():
    assert prompt_workers(default=5, input_fn=_menu_input([""])) == 5


def test_prompt_workers_accepts_integer():
    assert prompt_workers(default=5, input_fn=_menu_input(["9"])) == 9


def test_prompt_workers_reprompts_on_invalid_input():
    assert prompt_workers(default=5, input_fn=_menu_input(["abc", "0", "7"])) == 7


def test_prompt_workers_rejects_below_one():
    assert prompt_workers(default=5, input_fn=_menu_input(["0", "3"])) == 3


class _Args:
    def __init__(self, mode=None, workers=None):
        self.mode = mode
        self.workers = workers


def test_resolve_options_headless_bypasses_menu():
    """Any --mode means no interactive prompt at all."""

    def _boom(prompt=""):
        raise AssertionError("headless run must not prompt")

    mode, workers = resolve_runtime_options(_Args(mode="fan", workers=None),
                                            input_fn=_boom, print_fn=lambda *a, **k: None)
    assert mode == "fan"
    assert workers == 5  # default applied without prompting


def test_resolve_options_headless_respects_explicit_workers():
    mode, workers = resolve_runtime_options(_Args(mode="all", workers=3),
                                            input_fn=_menu_input([]),
                                            print_fn=lambda *a, **k: None)
    assert (mode, workers) == ("all", 3)


def test_resolve_options_menu_exit_returns_none():
    mode, workers = resolve_runtime_options(_Args(mode=None, workers=None),
                                            input_fn=_menu_input(["0"]),
                                            print_fn=lambda *a, **k: None)
    assert mode is None
    assert workers is None


def test_resolve_options_menu_prompts_workers():
    mode, workers = resolve_runtime_options(_Args(mode=None, workers=None),
                                            input_fn=_menu_input(["2", "8"]),
                                            print_fn=lambda *a, **k: None)
    assert (mode, workers) == ("fan", 8)


def test_resolve_options_menu_workers_default():
    mode, workers = resolve_runtime_options(_Args(mode=None, workers=None),
                                            input_fn=_menu_input(["1", ""]),
                                            print_fn=lambda *a, **k: None)
    assert (mode, workers) == ("all", 5)


def test_resolve_options_menu_keeps_explicit_workers():
    mode, workers = resolve_runtime_options(_Args(mode=None, workers=4),
                                            input_fn=_menu_input(["1"]),
                                            print_fn=lambda *a, **k: None)
    assert (mode, workers) == ("all", 4)


def test_main_menu_exit_terminates_cleanly(monkeypatch, capsys):
    """Choosing Exit prints the goodbye message and exits with status 0."""
    monkeypatch.setattr("switch_collector.parse_args",
                        lambda: _Args(mode=None, workers=None))
    monkeypatch.setattr("builtins.input", _menu_input(["0"]))

    import switch_collector
    with pytest.raises(SystemExit) as exc:
        switch_collector.main()

    assert exc.value.code == 0
    assert "Exiting. Goodbye!" in capsys.readouterr().out


# ==================== 12. ARUBAOS-CX 8400 MULTI-OS SUPPORT ====================
# Real ArubaOS-CX 8400 (JL375A Base Chassis) CLI samples.

ARUBAOS_CX_SYSTEM = """
Hostname             : CSW01-MD-LT2-PRIMARY
System Description   : JL375A 8400 Base Chassis
ArubaOS-CX Version   : XL.10.04.3050
Chassis Serial Nbr   : SG70K2G034
Management IPv4      : 172.21.255.1
System Up Time       : 21 days, 4 hours, 18 minutes
"""


def _cx_fan_output(working=18, total=18):
    """Builds an ArubaOS-CX `show environment fan` table across 3 trays."""
    lines = [
        "Fan information",
        "--------------------------------------------------------------------",
        "Tray Fan   Sensor            Status    Reading",
        "--------------------------------------------------------------------",
    ]
    index = 0
    broken = total - working
    for tray in (1, 2, 3):
        for slot in (1, 2, 3, 4, 5, 6):
            index += 1
            if index > total:
                break
            status = "ok"
            reading = 4450
            if broken > 0:
                status, reading, broken = "failed", 0, broken - 1
            lines.append("1/{}/{}      FAN{:<14} {:<9} {}".format(
                tray, slot, index, status, reading))
    return "\n".join(lines)


ARUBAOS_CX_LLDP = """
 LLDP neighbor-information
Port        System Name                 Chassis ID     Port ID
1/1/1       SW-ACCESS-01                aa:bb:cc:dd    GigabitEthernet1/0/1
1/1/3       HUAWEI-S5730                ee:ff:00:11    GigabitEthernet0/0/1
1/2/4       HUAWEI-AP8630               22:33:44:55    eth0
1/2/5       SW-DIST-01                  66:77:88:99    GigabitEthernet1/0/2
"""


# ---------- 1. System information / serial number ----------

def test_sn_parser_arubaos_cx():
    """ArubaOS-CX `show system` maps Hostname / Chassis Serial Nbr / ArubaOS-CX Version."""
    results = parse_system_information(ARUBAOS_CX_SYSTEM)

    assert len(results) == 1
    row = results[0]
    assert row["hostname"] == "CSW01-MD-LT2-PRIMARY"
    assert row["serial_number"] == "SG70K2G034"
    assert row["rom_version"] == "XL.10.04.3050"
    # A CX chassis is a single physical member.
    assert row["hostname"] == "CSW01-MD-LT2-PRIMARY"


def test_sn_parser_arubaos_cx_system_description_as_rom():
    """`System Description` is accepted as a firmware-version fallback."""
    output = """
Hostname             : CX-ALT
System Description   : XL.10.09.1000
Chassis Serial Nbr   : SG70K2G999
"""
    results = parse_system_information(output)
    assert results[0]["rom_version"] == "XL.10.09.1000"
    assert results[0]["serial_number"] == "SG70K2G999"


def test_sn_parser_arubaos_cx_uses_label_fallback():
    """A CX response without a Hostname falls back to the inventory label."""
    output = """
ArubaOS-CX Version   : XL.10.04.3050
Chassis Serial Nbr   : SG70K2G034
"""
    results = parse_system_information(output, label="PRIMARY-SW")
    assert results[0]["hostname"] == "PRIMARY-SW"


def test_sn_parser_procurve_still_supported():
    """The original ProCurve path must keep working unchanged."""
    output = """
  System Name        : lab-sw-02
  ROM Version        : WC.16.01.0010       Serial Number      : AB12CDE3FH
"""
    results = parse_system_information(output)
    assert results[0]["hostname"] == "lab-sw-02"
    assert results[0]["rom_version"] == "WC.16.01.0010"
    assert results[0]["serial_number"] == "AB12CDE3FH"


def test_sn_parser_arubaos_cx_missing_serial_still_raises():
    """A CX response with no serial number is still a ParseError."""
    output = """
Hostname             : CSW01
ArubaOS-CX Version   : XL.10.04.3050
"""
    with pytest.raises(ValueError) as exc:
        parse_system_information(output)
    assert "Serial Number" in str(exc.value)


# ---------- 2. Fan parser ----------

def test_fan_parser_arubaos_cx_environment_fan():
    """18 healthy fans across 3 trays report as {'1': '18/18'}."""
    result = parse_fan_output(_cx_fan_output(working=18, total=18))
    assert result == {"1": "18/18"}


def test_fan_parser_arubaos_cx_with_failed_fan():
    """A single failed fan reduces the ratio and triggers degradation."""
    result = parse_fan_output(_cx_fan_output(working=17, total=18))
    assert result == {"1": "17/18"}
    assert fan_is_degraded(result) is True


def test_fan_parser_arubaos_cx_all_fans_failed():
    result = parse_fan_output(_cx_fan_output(working=0, total=18))
    assert result == {"1": "0/18"}
    assert fan_is_degraded(result) is True


@pytest.mark.parametrize("status", ["ready", "failed", "fault", "down"])
def test_fan_parser_arubaos_cx_status_words(status):
    output = "Fan information\n1/1/1  FAN1  {}  4450\n1/1/2  FAN2  {}  4450".format(status, status)
    working, total = (2, 2) if status == "ready" else (0, 2)
    assert parse_fan_output(output) == {"1": "{}/{}".format(working, total)}


def test_fan_parser_procurve_still_supported():
    """ProCurve 'Fans in Failure State' parsing is unchanged."""
    output = " 0 / 4 Fans in Failure State\n"
    assert parse_fan_output(output) == {"1": "4/4"}


def test_fan_parser_cx_failure_becomes_warning_row():
    """A degraded CX fan turns the member row into a warning."""
    record = {"label": "CSW01", "ip": "172.21.255.1"}
    parsed = {
        "sn": [{"hostname": "CSW01-MD-LT2-PRIMARY",
                "serial_number": "SG70K2G034", "rom_version": "XL.10.04.3050"}],
        "fan": parse_fan_output(_cx_fan_output(working=17, total=18)),
        "poe": "Non-PoE",
        "huawei-count": {"1": 2},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])
    assert rows[0]["Status"] == "warning"
    assert rows[0]["FAN"] == "17/18"
    assert rows[0]["Solution Hint"] == HINT_FAN


# ---------- 3. PoE parser ----------

def test_poe_parser_non_poe_chassis():
    """A rejected PoE command on a core chassis yields 'Non-PoE'."""
    assert parse_power_output("Error: Invalid input 1/1") == "Non-PoE"
    assert parse_power_output("% Unknown command") == "Non-PoE"
    assert parse_power_output("Invalid command") == "Non-PoE"
    assert parse_power_output("This platform does not support PoE") == "Non-PoE"


def test_poe_parser_procurve_still_supported():
    output = """
  Total PoE Power     : 720 W
  Total Remaining Power : 512 W
"""
    assert parse_power_output(output) == "512 W"


def test_non_poe_counts_as_success_not_failure():
    """'Non-PoE' must not make the device partial or failed."""
    record = {"label": "CSW01", "ip": "172.21.255.1"}
    parsed = {
        "sn": [{"hostname": "CSW01", "serial_number": "SG70K2G034", "rom_version": "XL.10.04.3050"}],
        "fan": {"1": "18/18"},
        "poe": "Non-PoE",
        "huawei-count": {"1": 2},
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])
    assert rows[0]["Status"] == "success"
    assert rows[0]["PoE Remaining (W)"] == "Non-PoE"
    assert rows[0]["Solution Hint"] == ""


# ---------- 4. Huawei LLDP parser ----------

def test_huawei_lldp_counter_arubaos_cx_neighbor_info():
    """ArubaOS-CX Member/Slot/Port rows attribute to the first digit."""
    result = count_huawei_devices(ARUBAOS_CX_LLDP)
    # HUAWEI-S5730 on 1/1/3 and HUAWEI-AP8630 on 1/2/4, both member 1.
    assert result == {"1": 2}


def test_huawei_lldp_cx_neighbor_info_needs_no_separator_line():
    """CX output has no dashed separator; port-prefixed rows must still count.

    Regression guard: a parser that requires the ProCurve '---' separator
    silently reports zero Huawei neighbours on ArubaOS-CX.
    """
    output = """
 LLDP neighbor-information
Port        System Name        Chassis ID    Port ID
1/1/1       SW-ACCESS-01       aa:bb:cc:dd   GigabitEthernet1/0/1
1/1/3       HUAWEI-S5730       ee:ff:00:11   GigabitEthernet0/0/1
1/2/4       HUAWEI-AP8630      22:33:44:55   eth0
"""
    assert count_huawei_devices(output) == {"1": 2}


def test_huawei_lldp_cx_multi_member_without_separator():
    """Per-member attribution works on CX rows that have no separator."""
    output = """
 LLDP neighbor-information
1/1/1       HUAWEI-S5730        aa:bb:cc:dd   GigabitEthernet0/0/1
2/1/1       HUAWEI-S5731        ee:ff:00:11   GigabitEthernet0/0/1
2/2/2       HUAWEI-AP8630       22:33:44:55   eth0
"""
    assert count_huawei_devices(output) == {"1": 1, "2": 2}


def test_huawei_lldp_procurve_still_needs_data_region():
    """Non-port preamble lines must not be counted as neighbours."""
    output = """
  LLDP Remote Devices Information

  LocalPort | ChassisId                 PortId              PortDescr
  --------- + ------------------------- ------------------- -------------------------
  1/1       | a1 b2 c3 d4 e5 f6         1/1/1               HUAWEI S5720
  2/14      | a1 b2 c3 d4 e5 f7         2/1/1               HUAWEI S5730
"""
    assert count_huawei_devices(output) == {"1": 1, "2": 1}


def test_huawei_lldp_counter_cx_multi_member():
    """A CX multi-chassis line attributes each AP to its own member."""
    output = """
 LLDP neighbor-information
------------------------------------------------------------------------------------
1/1/1       HUAWEI-S5730        aa:bb:cc:dd    GigabitEthernet0/0/1
2/1/1       HUAWEI-S5731        ee:ff:00:11    GigabitEthernet0/0/1
2/2/2       HUAWEI-AP8630       22:33:44:55    eth0
1/2/3       SW-ACCESS-01        66:77:88:99    GigabitEthernet1/0/1
"""
    assert count_huawei_devices(output) == {"1": 1, "2": 2}


def test_huawei_lldp_counter_procurve_still_supported():
    """ProCurve pipe-delimited parsing is unchanged."""
    output = """
  LLDP Remote Devices Information

  LocalPort | ChassisId                 PortId              PortDescr
  --------- + ------------------------- ------------------- -------------------------
  1/1       | a1 b2 c3 d4 e5 f6         1/1/1               HUAWEI S5720
  2/14      | a1 b2 c3 d4 e5 f7         2/1/1               HUAWEI S5730
"""
    assert count_huawei_devices(output) == {"1": 1, "2": 1}


# ---------- 5. Command fallbacks ----------

class _RecordingConn:
    """Records every command and replies from a lookup table."""

    def __init__(self, table):
        self.table = table
        self.sent = []

    def send_command(self, cmd, read_timeout=None):
        self.sent.append(cmd)
        return self.table.get(cmd, "")


CX_COMMAND_TABLE = {
    "show system information": "Error: Invalid input 1/1",
    "show system": ARUBAOS_CX_SYSTEM,
    "show system fans": "Error: Invalid input 1/1",
    "show environment fan": _cx_fan_output(working=18, total=18),
    "show power-over-ethernet": "Error: Invalid input 1/1",
    "show lldp info remote-device": "Error: Invalid input 1/1",
    "show lldp neighbor-info": ARUBAOS_CX_LLDP,
}


@pytest.mark.parametrize("collector,primary,fallback", [
    ("sn", "show system information", "show system"),
    ("fan", "show system fans", "show environment fan"),
    ("huawei-count", "show lldp info remote-device", "show lldp neighbor-info"),
])
def test_collect_device_data_arubaos_cx_fallbacks(collector, primary, fallback):
    """Rejected ProCurve commands trigger the documented CX equivalent."""
    conn = _RecordingConn(CX_COMMAND_TABLE)
    out = run_with_fallback(conn, collector, primary, 45)

    assert conn.sent == [primary, fallback]
    assert "Invalid input" not in out


def test_collect_device_data_cx_poe_records_non_poe():
    """PoE has no fallback; a rejected command is recorded as 'Non-PoE'."""
    conn = _RecordingConn(CX_COMMAND_TABLE)
    out = run_with_fallback(conn, "poe", "show power-over-ethernet", 45)

    assert conn.sent == ["show power-over-ethernet"]
    assert out == "Non-PoE"


def test_collect_device_data_procurve_sends_no_fallback():
    """A working ProCurve switch must only ever send one command per collector."""
    table = {
        "show system information": "System Name : SW1\nROM Version : WC.16.01.0010\nSerial Number : CN1\n",
        "show system fans": "0 / 4 Fans in Failure State\n",
        "show power-over-ethernet": "Total Remaining Power : 512 W\n",
        "show lldp info remote-device": " 1/1 | aa | 1 | HUAWEI S5720\n",
    }
    for collector in ("sn", "fan", "poe", "huawei-count"):
        conn = _RecordingConn(table)
        run_with_fallback(conn, collector, COLLECTOR_COMMANDS[collector], 45)
        assert conn.sent == [COLLECTOR_COMMANDS[collector]], collector


def test_collect_device_data_cx_end_to_end_all_mode(monkeypatch):
    """A CX chassis collects cleanly across all four collectors in one session."""
    class MockConnect:
        def __init__(self, **kwargs):
            self.table = CX_COMMAND_TABLE
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def send_command(self, cmd, read_timeout=None):
            return self.table.get(cmd, "")

    monkeypatch.setattr("switch_collector.ConnectHandler", MockConnect)

    record = {"label": "PRIMARY SWITCH CORE", "ip": "172.21.255.1",
              "username": "admin", "password": "pwd"}
    res = collect_device_data(record, ["aruba_os"], 45, "all")

    assert res["status"] == "success"
    assert res["attempts"] == {"sn": 1, "fan": 1, "poe": 1, "huawei-count": 1}
    assert res["outputs"]["poe"] == "Non-PoE"

    parsed = process_parsed_data(
        outputs=res["outputs"], label=record["label"],
        collectors_to_run=["sn", "fan", "poe", "huawei-count"],
        attempts_dict=res["attempts"], errors_dict=res["errors"],
    )
    assert parsed["sn"][0]["serial_number"] == "SG70K2G034"
    assert parsed["sn"][0]["rom_version"] == "XL.10.04.3050"
    assert parsed["fan"] == {"1": "18/18"}
    assert parsed["poe"] == "Non-PoE"
    assert parsed["huawei-count"] == {"1": 2}


def test_collect_device_data_cx_fallback_on_empty_response(monkeypatch):
    """A valid but empty primary response also triggers the CX fallback."""
    seen = []

    class MockConnect:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def send_command(self, cmd, read_timeout=None):
            seen.append(cmd)
            if cmd == "show system fans":
                return "\n"
            return _cx_fan_output(working=18, total=18)

    monkeypatch.setattr("switch_collector.ConnectHandler", MockConnect)

    record = {"label": "CSW01", "ip": "1.1.1.1", "username": "admin", "password": "pwd"}
    res = collect_device_data(record, ["aruba_os"], 45, "fan")

    assert seen == ["show system fans", "show environment fan"]
    parsed = process_parsed_data(
        outputs=res["outputs"], label="CSW01", collectors_to_run=["fan"],
        attempts_dict=res["attempts"], errors_dict=res["errors"],
    )
    assert parsed["fan"] == {"1": "18/18"}


def test_cx_standalone_row_uses_member_one():
    """A CX chassis renders as a single physical member row."""
    record = {"label": "PRIMARY SWITCH CORE", "ip": "172.21.255.1"}
    parsed = {
        "sn": parse_system_information(ARUBAOS_CX_SYSTEM),
        "fan": parse_fan_output(_cx_fan_output(working=18, total=18)),
        "poe": "Non-PoE",
        "huawei-count": count_huawei_devices(ARUBAOS_CX_LLDP),
    }
    rows = build_member_rows(record, parsed, {}, "all",
                             ["sn", "fan", "poe", "huawei-count"])

    assert len(rows) == 1
    assert rows[0]["Member"] == "1"
    assert rows[0]["Serial Number"] == "SG70K2G034"
    assert rows[0]["ROM Version"] == "XL.10.04.3050"
    assert rows[0]["FAN"] == "18/18"
    assert rows[0]["Huawei AP Count"] == 2
    assert rows[0]["Status"] == "success"


# ==================== 13. PORTABLE RELEASE PACKAGING ====================
# Contract tests for start_collector.bat, setup.bat and the portable packager.

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
START_BAT = os.path.join(REPO_ROOT, "start_collector.bat")
SETUP_BAT = os.path.join(REPO_ROOT, "setup.bat")
PACKAGE_SCRIPT = os.path.join(REPO_ROOT, "scripts", "package_portable.ps1")
PORTABLE_ZIP = os.path.join(REPO_ROOT, "release", "Switch-Collector-v1.0.0-portable.zip")

STAGING_FOLDER = "Switch-Collector-Portable"

EXPECTED_ALLOWED_FILES = (
    "start_collector.bat",
    "setup.bat",
    "switch_collector.py",
    "requirements.txt",
    "switch.example.txt",
    "README.md",
)

# Every one of these must be rejected by the packaging guard.
EXPECTED_FORBIDDEN_NAMES = (
    "switch.txt", ".git", "__pycache__", ".pytest_cache", "logs",
    "outputs", "outputs_clean", "docs", "tests", "test",
    "switch_collector.pyc", "collector_20260928_100000.log",
    "switch_master_20260928_100000.xlsx", "sn_result.csv",
)


def _read_packaging_script():
    assert os.path.isfile(PACKAGE_SCRIPT), f"Missing packaging script: {PACKAGE_SCRIPT}"
    with open(PACKAGE_SCRIPT, "r", encoding="utf-8") as handle:
        return handle.read()


def _extract_ps_array(content, variable_name):
    """Pulls the quoted entries out of a PowerShell `@(...)` array.

    Accepts both quote styles: the packager uses single quotes for regex
    patterns so PowerShell does not interpolate their `$` anchors.
    """
    match = re.search(
        r"\$" + re.escape(variable_name) + r"\s*=\s*@\((.*?)^\s*\)",
        content, flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"Could not find PowerShell array ${variable_name}"
    pairs = re.findall(r"'([^']+)'|\"([^\"]+)\"", match.group(1))
    return [single or double for single, double in pairs]


def test_package_portable_script_exists():
    """The packaging script ships with the repository."""
    assert os.path.isfile(PACKAGE_SCRIPT), f"Missing packaging script: {PACKAGE_SCRIPT}"
    content = _read_packaging_script()

    # Parameters required by the release workflow.
    assert '[string]$Version = "1.0.0"' in content
    assert "[switch]$Force" in content

    # Staging and release layout.
    assert STAGING_FOLDER in content
    assert '"staging"' in content
    assert '"release"' in content
    assert 'Switch-Collector-v$Version-portable.zip' in content

    # Archive is produced with Compress-Archive and staging is cleaned up.
    assert "Compress-Archive" in content
    assert "Remove-Item -LiteralPath $StagingDir -Recurse" in content

    # It must never copy the repository wholesale.
    assert "Copy-Item -Path $RootDir -Recurse" not in content

    # Both guard gates and the credentials check are present.
    assert "Forbidden entries found in staging" in content
    assert "Forbidden entries found in ZIP" in content
    assert "must never be included" in content


def test_start_collector_bat_exists_and_references_inventory():
    """The launcher exists, checks python and switch.txt, and passes args through."""
    assert os.path.isfile(START_BAT), f"Missing launcher: {START_BAT}"
    with open(START_BAT, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "Starting Unified Switch Collector" in content
    # ASCII banner only, so the console never renders mojibake.
    assert content.isascii(), "launcher must be plain ASCII"
    assert "=" * 68 in content

    # Python availability check.
    assert "where python" in content

    # Inventory guard, with the copy-from-template guidance.
    assert 'if not exist "switch.txt"' in content
    assert "[ERROR] Inventory file switch.txt not found!" in content
    assert "copy switch.example.txt to switch.txt" in content
    assert "exit /b 1" in content

    # Working directories.
    assert "mkdir logs" in content
    assert "mkdir outputs" in content

    # Runs the collector and forwards every argument.
    assert "python switch_collector.py %*" in content
    assert "if %ERRORLEVEL% neq 0" in content
    assert "pause" in content


def test_setup_bat_exists_and_references_requirements():
    """The installer exists, checks python and installs requirements."""
    assert os.path.isfile(SETUP_BAT), f"Missing installer: {SETUP_BAT}"
    with open(SETUP_BAT, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "Unified Switch Collector - Automated Setup" in content
    assert content.isascii(), "installer must be plain ASCII"
    assert "where python" in content
    assert "pip install -r requirements.txt" in content
    assert "mkdir logs" in content
    assert "mkdir outputs" in content
    assert "Setup Complete" in content
    assert "pause" in content


def test_packaging_forbidden_files_excluded():
    """The guard patterns catch every sensitive or generated path."""
    content = _read_packaging_script()
    patterns = _extract_ps_array(content, "ForbiddenPatterns")
    allowed = _extract_ps_array(content, "AllowedFiles")

    assert tuple(allowed) == EXPECTED_ALLOWED_FILES

    # Every forbidden name must match at least one pattern.
    unmatched = [
        name for name in EXPECTED_FORBIDDEN_NAMES
        if not any(re.search(pattern, name) for pattern in patterns)
    ]
    assert not unmatched, f"Forbidden names not caught by the guard: {unmatched}"

    # The credential file must be explicitly forbidden by name.
    assert any(re.search(p, "switch.txt") for p in patterns)

    # The allowlisted files must not trip the guard (no false positives).
    false_positives = [
        name for name in EXPECTED_ALLOWED_FILES
        if any(re.search(pattern, name) for pattern in patterns)
    ]
    assert not false_positives, f"Allowlisted files falsely flagged: {false_positives}"

    # switch.example.txt must ship while switch.txt must not.
    assert "switch.example.txt" in allowed
    assert "switch.txt" not in allowed


def test_portable_zip_contents():
    """The built archive contains the allowlist and zero forbidden files."""
    if not os.path.isfile(PORTABLE_ZIP):
        pytest.skip(
            "Portable archive not built. Run: "
            "powershell -File scripts\\package_portable.ps1 -Force"
        )

    with zipfile.ZipFile(PORTABLE_ZIP) as archive:
        names = archive.namelist()

    # Every allowlisted file is present under the single staging folder.
    for relative in EXPECTED_ALLOWED_FILES:
        assert f"{STAGING_FOLDER}/{relative}" in names, f"Missing from archive: {relative}"

    # Exactly one top-level folder.
    top_level = {name.split("/")[0] for name in names if name.strip("/")}
    assert top_level == {STAGING_FOLDER}, f"Unexpected top-level entries: {top_level}"

    # No forbidden entry, most importantly no credentials.
    segments = {segment for name in names for segment in name.split("/") if segment}
    assert "switch.txt" not in segments, "Credential file leaked into the archive!"
    assert not any(segment.endswith(".pyc") for segment in segments)
    assert not any(segment.endswith(".log") for segment in segments)
    assert not any(segment.endswith(".xlsx") for segment in segments)
    assert not any(segment.endswith(".csv") for segment in segments)
    for generated in ("logs", "outputs", "outputs_clean", "docs", "tests", "__pycache__"):
        assert generated not in segments, f"Generated directory leaked: {generated}"
    assert ".git" not in segments

    # The safe template is what operators receive.
    assert f"{STAGING_FOLDER}/switch.example.txt" in names


def test_gitignore_excludes_packaging_artifacts():
    """Build and release directories must never be committed."""
    gitignore = os.path.join(REPO_ROOT, ".gitignore")
    with open(gitignore, "r", encoding="utf-8") as handle:
        content = handle.read()
    for directory in ("staging/", "release/", "logs/", "outputs/"):
        assert directory in content
    # Real credentials stay ignored.
    assert "switch.txt" in content


# ==================== 14. STANDALONE EXECUTABLE (PYINSTALLER) ====================

SPEC_FILE = os.path.join(REPO_ROOT, "switch_collector.spec")
BUILD_SCRIPT = os.path.join(REPO_ROOT, "scripts", "build_exe.ps1")
DIST_EXE = os.path.join(REPO_ROOT, "dist", "Switch-Collector", "Switch-Collector.exe")
DIST_INTERNAL = os.path.join(REPO_ROOT, "dist", "Switch-Collector", "_internal")
BUNDLE_EXE_NAME = "Switch-Collector.exe"
BUNDLE_INTERNAL_NAME = "_internal"


def test_switch_collector_spec_exists():
    """The PyInstaller spec declares an onedir console bundle."""
    assert os.path.isfile(SPEC_FILE), f"Missing PyInstaller spec: {SPEC_FILE}"
    with open(SPEC_FILE, "r", encoding="utf-8") as handle:
        content = handle.read()

    # onedir layout: exclude_binaries on the EXE plus a COLLECT step.
    assert "EXE(" in content
    assert "exclude_binaries=True" in content
    assert 'name="Switch-Collector"' in content
    assert "console=True" in content
    assert "COLLECT(" in content

    # Entry point and bundle targets.
    assert '["switch_collector.py"]' in content
    assert 'pathex=[PROJECT_ROOT]' in content

    # Netmiko drivers resolve by name at runtime, so they must be hidden imports.
    for module in ("netmiko", "netmiko.cisco", "netmiko.hp", "netmiko.aruba",
                   "openpyxl", "paramiko", "scp", "cryptography"):
        assert f'"{module}"' in content, f"missing hidden import: {module}"
    assert "collect_submodules(\"netmiko\")" in content
    assert "collect_data_files(\"netmiko\")" in content

    # Test-only packages must stay out of the bundle.
    for excluded in ("pytest", "hypothesis", "playwright"):
        assert excluded in content


def test_build_exe_script_exists():
    """The build script resolves PyInstaller, cleans, builds and verifies."""
    assert os.path.isfile(BUILD_SCRIPT), f"Missing build script: {BUILD_SCRIPT}"
    with open(BUILD_SCRIPT, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "pyinstaller" in content.lower()
    assert "-y" in content
    assert "switch_collector.spec" in content
    # Cleans previous output before rebuilding.
    assert "build" in content
    assert "dist" in content
    assert "Remove-Item" in content
    # Verifies both the exe and the _internal runtime directory.
    assert "Switch-Collector.exe" in content
    assert "_internal" in content
    assert "exit 0" in content


def test_start_collector_bat_prioritizes_exe():
    """The launcher runs the bundled exe first, so Python is never required."""
    assert os.path.isfile(START_BAT), f"Missing launcher: {START_BAT}"
    with open(START_BAT, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert content.isascii(), "launcher must be plain ASCII"

    # The exe branch must come BEFORE the python fallback.
    exe_index = content.index('if exist "Switch-Collector.exe"')
    python_index = content.index("where python")
    assert exe_index < python_index, "the .exe must be preferred over Python"

    assert "Switch-Collector.exe %*" in content
    assert "goto :after_run" in content
    # Source-checkout fallback is retained.
    assert "python switch_collector.py %*" in content
    # Neither available is a hard failure.
    assert "Neither Switch-Collector.exe nor Python" in content
    assert "exit /b 1" in content


def test_base_dir_prefers_executable_folder_when_frozen():
    """A frozen build must resolve switch.txt next to the .exe, not _internal.

    Regression guard: PyInstaller points __file__ inside the _internal runtime
    directory, so using it directly made the portable release look for
    switch.txt in _internal\\ and fail on a clean machine.
    """
    import switch_collector as sc

    assert hasattr(sc, "BASE_DIR")

    with open(os.path.join(REPO_ROOT, "switch_collector.py"), "r", encoding="utf-8") as handle:
        source = handle.read()

    # Frozen builds resolve the base directory from the executable location.
    assert 'getattr(sys, "frozen", False)' in source
    assert "sys.executable" in source
    assert 'BASE_DIR / "switch.txt"' in source
    assert 'BASE_DIR / "outputs"' in source
    assert "BASE_DIR / log_dir" in source

    # In a source checkout BASE_DIR is the script's own folder.
    assert sc.BASE_DIR == Path(sc.__file__).resolve().parent


def test_portable_zip_contains_bundled_executable_and_internal():
    """The release archive ships a runnable exe plus its _internal runtime."""
    if not os.path.isfile(PORTABLE_ZIP):
        pytest.skip(
            "Portable archive not built. Run: "
            "powershell -File scripts\\package_portable.ps1 -Force"
        )

    with zipfile.ZipFile(PORTABLE_ZIP) as archive:
        names = archive.namelist()

    prefix = f"{STAGING_FOLDER}/"

    # The frozen executable is the whole point of the portable release.
    assert f"{prefix}{BUNDLE_EXE_NAME}" in names, "bundled executable missing"

    # Its runtime directory must ship too, or the exe cannot start.
    internal_entries = [n for n in names if n.startswith(f"{prefix}{BUNDLE_INTERNAL_NAME}/")]
    assert internal_entries, f"{BUNDLE_INTERNAL_NAME} runtime missing from archive"

    # Every loose file from the allowlist ships alongside it.
    for relative in EXPECTED_ALLOWED_FILES:
        assert f"{prefix}{relative}" in names, f"Missing from archive: {relative}"

    # Exactly one top-level folder.
    top_level = {n.split("/")[0] for n in names if n.strip("/")}
    assert top_level == {STAGING_FOLDER}

    # Zero credentials anywhere, including inside the bundle.
    segments = {s for n in names for s in n.split("/") if s}
    assert "switch.txt" not in segments, "Credential file leaked into the archive!"
    assert f"{prefix}switch.example.txt" in names

    # No generated reports or logs outside the frozen runtime.
    loose = [n for n in names if not n.startswith(f"{prefix}{BUNDLE_INTERNAL_NAME}/")]
    assert not any(n.endswith(".xlsx") for n in loose)
    assert not any(n.endswith(".csv") for n in loose)
    assert not any(n.endswith(".log") for n in loose)
    for generated in ("logs", "outputs", "outputs_clean", "docs", "tests", "__pycache__", ".git"):
        assert generated not in {s for n in loose for s in n.split("/")}


def test_package_portable_script_bundles_frozen_runtime():
    """The packager requires the frozen bundle and exempts _internal bytecode."""
    content = _read_packaging_script()

    # Refuses to ship a bundle without the executable.
    assert "Run .\\scripts\\build_exe.ps1 first." in content
    assert 'dist\\Switch-Collector' in content or 'dist/Switch-Collector' in content
    assert "Cannot find dist/Switch-Collector/Switch-Collector.exe" in content

    # Copies the whole frozen bundle, then the loose allowlist files.
    assert "Get-ChildItem -LiteralPath $DistDir" in content
    assert "Copy-Item -LiteralPath $Entry.FullName" in content
    assert "Copy-Item -Path $RootDir -Recurse" not in content

    # Verifies exe and _internal both landed in staging.
    assert "Bundled executable is missing from staging" in content
    assert "Bundled runtime directory _internal is missing from staging" in content

    # _internal holds frozen bytecode, so build-artefact rules skip it there.
    assert "$InternalSkippedPatterns" in content
    assert "Test-InsideBundle" in content

    # The allowlist still excludes the credential file.
    allowed = _extract_ps_array(content, "AllowedFiles")
    assert tuple(allowed) == EXPECTED_ALLOWED_FILES
    assert "switch.txt" not in allowed


def test_gitignore_excludes_build_artifacts():
    """PyInstaller output must never be committed."""
    with open(os.path.join(REPO_ROOT, ".gitignore"), "r", encoding="utf-8") as handle:
        content = handle.read()
    for directory in ("build/", "dist/", "staging/", "release/"):
        assert directory in content
