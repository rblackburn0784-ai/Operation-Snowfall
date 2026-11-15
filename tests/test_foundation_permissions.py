from snowfall.core.permissions import is_host, is_staff, permitted_guild

def test_guild_restrictions():
    assert permitted_guild(99, 99)
    assert not permitted_guild(100, 99)
    assert not permitted_guild(None, 99)

def test_only_named_hosts_get_lifecycle_access():
    hosts, staff = frozenset({111}), frozenset({999})
    assert is_host(111, hosts)
    assert is_staff(111, hosts, staff, frozenset())
    assert is_staff(222, hosts, staff, frozenset({999}))
    assert not is_host(222, hosts)
    assert not is_staff(333, hosts, staff, frozenset({123}))
