import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock, call

import pytest

os.environ["MAXVPN_APPLIANCE_ROOT"] = tempfile.mkdtemp(prefix="maxvpn-empty-domains-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as appliance  # noqa: E402


@pytest.mark.parametrize("domains", [[], ["example.test"]])
def test_apply_without_previous_domain_option_can_repeat(monkeypatch, domains):
    monkeypatch.setattr(appliance, "find_ipset_section", lambda name: "dhcp.direct")
    run = Mock(return_value=subprocess.CompletedProcess([], 1))
    shell = Mock()
    monkeypatch.setattr(appliance, "run", run)
    monkeypatch.setattr(appliance, "shell", shell)

    appliance.update_dnsmasq_domains(domains)
    appliance.update_dnsmasq_domains(domains)

    assert (
        run.call_args_list
        == [call(["uci", "-q", "get", "dhcp.direct.domain"], check=False)] * 2
    )
    assert shell.call_args_list.count(call("uci commit dhcp")) == 2
    assert shell.call_args_list.count(call("/etc/init.d/dnsmasq reload")) == 2
    if domains:
        assert (
            shell.call_args_list.count(
                call("uci add_list dhcp.direct.domain=example.test")
            )
            == 2
        )


def test_failure_to_delete_existing_domains_still_aborts(monkeypatch):
    monkeypatch.setattr(appliance, "find_ipset_section", lambda name: "dhcp.direct")
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0),
            RuntimeError("UCI write failed"),
        ]
    )
    shell = Mock()
    monkeypatch.setattr(appliance, "run", run)
    monkeypatch.setattr(appliance, "shell", shell)

    with pytest.raises(RuntimeError, match="UCI write failed"):
        appliance.update_dnsmasq_domains([])
    shell.assert_not_called()
