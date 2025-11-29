# Example plugin (MVP)

This folder contains a minimal `manifest.json` used to demonstrate the `PluginLoader` discovery and the `/api/plugins` endpoint.

How to test:

- Ensure `core_service` is running (admin panel on port `11000`).
- Request discovered plugins:

```bash
curl -s http://127.0.0.1:11000/api/plugins | jq .
```

You should see `example_plugin` in the returned list (manifest contents).

Notes and next steps:
- This example is metadata-only: the loader reads `manifest.json` and exposes capabilities. The plugin code is not executed in-process.
- For real plugins you can implement:
  - adapter in `core_service/plugins/<name>` to interact with external APIs (Yandex, Proxmox), or
  - runner on agents (`client_manager/plugins/<name>`) to perform actions locally.
- To install a plugin from a git repo use the admin endpoint:

```bash
curl -X POST http://127.0.0.1:11000/api/plugins/install -H 'Content-Type: application/json' \
  -d '{"git_url":"https://github.com/yourorg/your-plugin.git"}'
```

The MVP installer simply clones the repo into `core_service/plugins/` and attempts to read `manifest.json`.
