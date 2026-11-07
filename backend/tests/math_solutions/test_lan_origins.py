from types import SimpleNamespace
from unittest.mock import patch
from app.math_ink.lan import lan_origins


def test_dynamic_lan_origins_follow_host_address_changes_without_trusting_arbitrary_private_hosts():
    settings = SimpleNamespace(lan_mode=True, app_env="development", lan_frontend_port=3050)
    with patch("app.math_ink.lan.host_addresses", return_value={"192.168.1.20", "8.8.8.8"}):
        origins = lan_origins(settings)
        assert "http://192.168.1.20:3050" in origins
        assert "http://localhost:3050" in origins
        assert "http://192.168.1.21:3050" not in origins
        assert "http://192.168.1.20:3000" not in origins
        assert "http://8.8.8.8:3050" not in origins
    with patch("app.math_ink.lan.host_addresses", return_value={"10.2.1.7"}):
        assert "http://10.2.1.7:3050" in lan_origins(settings)
        assert "http://192.168.1.20:3050" not in lan_origins(settings)


def test_lan_is_opt_in_development_only_and_discovery_failure_has_no_wildcard():
    settings = SimpleNamespace(lan_mode=False, app_env="development", lan_frontend_port=3050)
    assert lan_origins(settings) == set()
    settings.lan_mode = True
    settings.app_env = "production"
    assert lan_origins(settings) == set()
    settings.app_env = "development"
    with patch("app.math_ink.lan.host_addresses", side_effect=OSError()):
        assert lan_origins(settings) == {"http://localhost:3050", "http://127.0.0.1:3050"}
