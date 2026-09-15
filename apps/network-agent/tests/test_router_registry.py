from pathlib import Path
from uuid import uuid4

from app.core.router_registry import RouterRegistry


def test_resolves_a_known_router_id(tmp_path: Path) -> None:
    router_id = uuid4()
    registry_file = tmp_path / "routers.yaml"
    registry_file.write_text(
        f"""
routers:
  {router_id}:
    host: 10.90.0.2
    username: agent
    password: secret
""",
        encoding="utf-8",
    )

    registry = RouterRegistry(registry_file)
    connection = registry.resolve(router_id)

    assert connection is not None
    assert connection.host == "10.90.0.2"
    assert connection.username == "agent"
    assert connection.password == "secret"
    assert connection.use_ssl is True  # default
    assert connection.api_ssl_port == 8729  # default


def test_unknown_router_id_resolves_to_none(tmp_path: Path) -> None:
    registry_file = tmp_path / "routers.yaml"
    registry_file.write_text("routers: {}\n", encoding="utf-8")

    registry = RouterRegistry(registry_file)

    assert registry.resolve(uuid4()) is None


def test_missing_registry_file_resolves_to_none_rather_than_erroring(tmp_path: Path) -> None:
    registry = RouterRegistry(tmp_path / "does-not-exist.yaml")

    assert registry.resolve(uuid4()) is None


def test_registry_never_accepts_a_host_from_the_caller(tmp_path: Path) -> None:
    """The whole point of this registry: resolve(router_id) takes only a
    UUID. There is no method on RouterRegistry that accepts a host/IP —
    this test documents that as an explicit contract, not just an absence."""
    import inspect

    resolve_params = list(inspect.signature(RouterRegistry.resolve).parameters)
    assert resolve_params == ["self", "router_id"]
