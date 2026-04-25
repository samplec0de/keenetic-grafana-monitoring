"""Lightweight sanity tests for the multi-instance patches.

Run from repo root:
    .venv/bin/python tests_multi_instance.py
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap

from influxdb_writter import InfuxWriter


def test_extra_tags_loaded_from_config():
    cfg = textwrap.dedent("""
        [influx2]
        url=http://example.invalid:8086
        org=o
        token=t
        bucket=b
        timeout=1000

        [tags]
        router=home
        site=moscow
    """)
    with tempfile.NamedTemporaryFile('w', suffix='.ini', delete=False) as f:
        f.write(cfg)
        path = f.name
    try:
        # Load extra tags without constructing the InfluxDB client.
        tags = InfuxWriter._load_extra_tags(path)
        assert tags == {'router': 'home', 'site': 'moscow'}, tags
        print('  OK  extra tags loaded correctly')
    finally:
        os.unlink(path)


def test_no_tags_section_returns_empty():
    cfg = textwrap.dedent("""
        [influx2]
        url=http://example.invalid:8086
        org=o
        token=t
        bucket=b
        timeout=1000
    """)
    with tempfile.NamedTemporaryFile('w', suffix='.ini', delete=False) as f:
        f.write(cfg)
        path = f.name
    try:
        assert InfuxWriter._load_extra_tags(path) == {}
        print('  OK  missing [tags] section yields empty dict (backward compat)')
    finally:
        os.unlink(path)


def test_config_dir_env_is_honored():
    """Run the exporter as a subprocess with KEENETIC_CONFIG_DIR pointing at a
    bogus config. The process should attempt to read from that location and
    fail there (not at the source-tree default)."""
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, 'config'))
    # Write the minimum needed for import of metrics.json (empty metrics list).
    with open(os.path.join(tmp, 'config', 'metrics.json'), 'w') as f:
        json.dump({'metrics': []}, f)
    # Intentionally: no config.ini. The script should fail on missing keenetic
    # section — proving it read from our dir, not from the repo's config/.
    env = dict(os.environ, KEENETIC_CONFIG_DIR=tmp)
    result = subprocess.run(
        [sys.executable, 'keentic_influxdb_exporter.py'],
        capture_output=True, text=True, timeout=15, env=env,
    )
    combined = result.stdout + result.stderr
    assert 'keenetic' in combined.lower() or 'KeyError' in combined, combined
    print('  OK  KEENETIC_CONFIG_DIR redirects config lookup')


def test_dashboard_json_valid_and_has_router_var():
    with open('grafana-dashboard.json') as f:
        d = json.load(f)
    names = [v.get('name') for v in d.get('templating', {}).get('list', [])]
    assert 'router' in names, names
    # ensure every $timeFilter query now has the router filter
    missing = []
    def walk(o):
        if isinstance(o, dict):
            q = o.get('query')
            if isinstance(q, str) and '$timeFilter' in q and '"router"' not in q:
                missing.append(q[:80])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    assert not missing, f'queries missing router filter: {missing}'
    print('  OK  dashboard has router var + filter on all timeFilter queries')


def test_write_metrics_applies_extra_tags():
    """Construct an InfuxWriter and call write_metrics with a stub client to
    verify that extra tags are merged into each point's tags before write."""
    cfg = textwrap.dedent("""
        [influx2]
        url=http://example.invalid:8086
        org=o
        token=t
        bucket=b
        timeout=1000

        [tags]
        router=home
    """)
    with tempfile.NamedTemporaryFile('w', suffix='.ini', delete=False) as f:
        f.write(cfg)
        path = f.name
    try:
        # Build InfuxWriter but replace the write_api with a recorder.
        import configparser
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path)
        w = InfuxWriter.__new__(InfuxWriter)
        w._configuration = cp['influx2']
        w._extra_tags = InfuxWriter._load_extra_tags(path)
        captured = []
        class FakeWriteApi:
            def write(self, **kwargs):
                captured.append(kwargs['record'])
        w._write_api = FakeWriteApi()

        metrics = [
            {'measurement': 'system', 'tags': {'cpu': '0'}, 'fields': {'load': 0.5}},
            {'measurement': 'interface', 'fields': {'rx': 100}},  # no tags key
        ]
        w.write_metrics(metrics)
        assert captured, 'writer never called'
        sent = captured[0]
        assert sent[0]['tags'] == {'cpu': '0', 'router': 'home'}, sent[0]
        assert sent[1]['tags'] == {'router': 'home'}, sent[1]
        print('  OK  write_metrics merges extra tags (existing + missing tags key)')
    finally:
        os.unlink(path)


if __name__ == '__main__':
    tests = [
        test_extra_tags_loaded_from_config,
        test_no_tags_section_returns_empty,
        test_config_dir_env_is_honored,
        test_write_metrics_applies_extra_tags,
        test_dashboard_json_valid_and_has_router_var,
    ]
    failures = 0
    for t in tests:
        print(f'{t.__name__}')
        try:
            t()
        except AssertionError as e:
            print(f'  FAIL  {e}')
            failures += 1
        except Exception as e:
            print(f'  ERROR  {type(e).__name__}: {e}')
            failures += 1
    if failures:
        print(f'\n{failures} failure(s)')
        sys.exit(1)
    print('\nall tests passed')
