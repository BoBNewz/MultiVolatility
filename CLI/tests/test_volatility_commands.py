"""Tests for MultiVolatility2 and MultiVolatility3 get_commands() — pure YAML logic."""

import pytest

# YAML files are named vol2_windows.full.yaml / vol2_linux.full.yaml etc.
WINDOWS_KEY = "windows.full"
LINUX_KEY = "linux.full"


class TestMultiVolatility2Commands:
    def setup_method(self):
        from multivol.multi_volatility2 import MultiVolatility2

        self.vol2 = MultiVolatility2()

    def test_get_commands_windows_returns_list(self):
        commands = self.vol2.get_commands(WINDOWS_KEY)
        assert isinstance(commands, list)
        assert len(commands) > 0

    def test_get_commands_windows_items_are_strings(self):
        commands = self.vol2.get_commands(WINDOWS_KEY)
        assert all(isinstance(c, str) for c in commands)

    def test_get_commands_linux_returns_list(self):
        commands = self.vol2.get_commands(LINUX_KEY)
        assert isinstance(commands, list)
        assert len(commands) > 0

    def test_get_commands_linux_items_are_strings(self):
        commands = self.vol2.get_commands(LINUX_KEY)
        assert all(isinstance(c, str) for c in commands)

    def test_get_commands_unknown_os_raises(self):
        with pytest.raises(FileNotFoundError):
            self.vol2.get_commands("freebsd")


class TestMultiVolatility3Commands:
    def setup_method(self):
        from multivol.multi_volatility3 import MultiVolatility3

        self.vol3 = MultiVolatility3()

    def test_get_commands_windows_returns_list(self):
        commands = self.vol3.get_commands(WINDOWS_KEY)
        assert isinstance(commands, list)
        assert len(commands) > 0

    def test_get_commands_windows_items_are_strings(self):
        commands = self.vol3.get_commands(WINDOWS_KEY)
        assert all(isinstance(c, str) for c in commands)

    def test_get_commands_linux_returns_list(self):
        commands = self.vol3.get_commands(LINUX_KEY)
        assert isinstance(commands, list)
        assert len(commands) > 0

    def test_get_commands_linux_items_are_strings(self):
        commands = self.vol3.get_commands(LINUX_KEY)
        assert all(isinstance(c, str) for c in commands)

    def test_get_commands_unknown_os_raises(self):
        with pytest.raises(FileNotFoundError):
            self.vol3.get_commands("freebsd")
