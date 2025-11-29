"""Simple plugin loader for core_service.

This is an MVP loader: it scans subdirectories of `plugins/` for a `manifest.json` file
and loads metadata. It does not execute plugin code in-process (safe option).
"""
from __future__ import annotations

import os
import json
from typing import Dict, Any, List


class PluginInfo(dict):
    pass


class PluginLoader:
    def __init__(self, plugins_path: str | None = None):
        self.plugins_path = plugins_path or os.path.join(os.path.dirname(__file__), '.')
        self._registry: Dict[str, PluginInfo] = {}

    def discover(self) -> List[PluginInfo]:
        """Discover plugins by scanning directories for manifest.json."""
        plugins = []
        base = os.path.abspath(self.plugins_path)
        if not os.path.isdir(base):
            return []
        for entry in os.listdir(base):
            p = os.path.join(base, entry)
            if not os.path.isdir(p):
                continue
            manifest_path = os.path.join(p, 'manifest.json')
            if not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                name = data.get('name') or entry
                info = PluginInfo(data)
                info['__path__'] = p
                self._registry[name] = info
                plugins.append(info)
            except Exception:
                # ignore malformed manifests
                continue
        return plugins

    def list_plugins(self) -> Dict[str, PluginInfo]:
        if not self._registry:
            self.discover()
        return self._registry

    def get(self, name: str) -> PluginInfo | None:
        return self.list_plugins().get(name)

    def install_from_git(self, git_url: str, dest_dir: str | None = None) -> Dict[str, Any]:
        """Minimal installer: clone a git repo into plugins dir. Returns manifest if found.

        Note: this is a naive implementation for MVP and assumes `git` available.
        """
        import subprocess
        base = os.path.abspath(self.plugins_path)
        if dest_dir:
            target = os.path.abspath(dest_dir)
        else:
            repo_name = os.path.splitext(os.path.basename(git_url))[0]
            target = os.path.join(base, repo_name)
        if os.path.exists(target):
            return {'ok': False, 'reason': 'target_exists', 'path': target}
        try:
            subprocess.check_call(['git', 'clone', git_url, target], cwd=base)
        except Exception as e:
            return {'ok': False, 'reason': 'git_clone_failed', 'error': str(e)}
        # attempt to read manifest
        manifest_path = os.path.join(target, 'manifest.json')
        if not os.path.exists(manifest_path):
            return {'ok': True, 'installed': True, 'manifest': None, 'path': target}
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # refresh registry
            self._registry[data.get('name') or os.path.basename(target)] = PluginInfo(data)
            return {'ok': True, 'installed': True, 'manifest': data, 'path': target}
        except Exception as e:
            return {'ok': True, 'installed': True, 'manifest': None, 'path': target, 'warning': str(e)}
