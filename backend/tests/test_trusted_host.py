import pytest


def test_unknown_host_is_rejected(client):
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:8005", "localhost:8000"])
def test_local_hosts_are_allowed(client, host):
    assert client.get("/health", headers={"Host": host}).status_code != 400
