#!/usr/bin/env python
"""Prints ping and target-access query stats along with built-in memcached stats."""

import yaml

from app.stats import get_stats

print(yaml.dump(get_stats(), default_flow_style=False))
