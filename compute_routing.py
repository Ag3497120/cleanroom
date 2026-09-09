"""Owner-configured compute slots. Public requests cannot choose network endpoints."""
from urllib.parse import urlsplit
from gateway_policy import Refused, validate_pair


def loopback_endpoint(value):
    u = urlsplit(value)
    if (u.scheme != 'http' or u.hostname != '127.0.0.1' or not u.port
            or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment):
        raise ValueError('Compute endpoints must be explicit loopback HTTP ports; use SSH forwarding for another Mac')
    return value.rstrip('/')


def small_pair(models):
    candidates = sorted((m for m in models if m.get('parameters') and m['provider'] == 'ollama'),
                        key=lambda m: (-m['parameters'], m['name']))
    # Keep the larger model for implementation; never guess sizes from model names.
    for implementation in candidates:
        for inspection in candidates:
            if (inspection['name'] != implementation['name'] and inspection['digest'] != implementation['digest']
                    and inspection['parameters'] + implementation['parameters'] <= 10_000_000_000):
                return validate_pair(models, inspection['name'], implementation['name'])
    raise Refused('COMPUTE_BUSY')
