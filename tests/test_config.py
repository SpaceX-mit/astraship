import pytest

from astraship.config import KernelConfig, resolve_kernel_command
from astraship.errors import KernelConfigError, KernelNotFoundError


def test_explicit_command_wins_over_environment_and_path() -> None:
    config = KernelConfig(command=("/configured/felix", "--stdio"))

    result = resolve_kernel_command(
        config,
        environ={"ASTRASHIP_FELIX_COMMAND": "/environment/felix"},
        which=lambda name: "/path/felix" if name == "felix-server" else None,
    )

    assert result == ("/configured/felix", "--stdio")


def test_environment_command_is_shell_tokenized_when_config_is_unset() -> None:
    config = KernelConfig()

    result = resolve_kernel_command(
        config,
        environ={"ASTRASHIP_FELIX_COMMAND": 'felix-server --mode "stdio server"'},
        which=lambda _: None,
    )

    assert result == ("felix-server", "--mode", "stdio server")


def test_path_fallback_resolves_felix_server() -> None:
    result = resolve_kernel_command(
        KernelConfig(),
        environ={},
        which=lambda name: "/usr/local/bin/felix-server" if name == "felix-server" else None,
    )

    assert result == ("/usr/local/bin/felix-server",)


@pytest.mark.parametrize(
    "config,environ",
    [
        (KernelConfig(command=()), {}),
        (KernelConfig(), {"ASTRASHIP_FELIX_COMMAND": "   "}),
    ],
)
def test_empty_command_is_rejected(config: KernelConfig, environ: dict[str, str]) -> None:
    with pytest.raises(KernelConfigError, match="cannot be empty"):
        resolve_kernel_command(config, environ=environ, which=lambda _: None)


def test_missing_command_describes_all_discovery_options() -> None:
    with pytest.raises(
        KernelNotFoundError, match="kernel.command.*ASTRASHIP_FELIX_COMMAND.*felix-server"
    ):
        resolve_kernel_command(KernelConfig(), environ={}, which=lambda _: None)
