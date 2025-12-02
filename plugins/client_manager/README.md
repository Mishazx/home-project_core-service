Client Manager plugin manifest (docker delivery)

This manifest describes `client_manager` as a plugin that can be installed via Docker. The registry `PluginVersion` should point `artifact_url` to the Docker image name (e.g. `mishazx/client_manager:0.1.0`).

Install flow (MVP):
- Core creates `PluginInstallJob` and forwards `admin.install_plugin` message to the target agent (client_manager).
- `client_manager` receives `admin.install_plugin`, performs `docker pull` and `docker run`.
- `client_manager` posts progress and final status back to Core at `/api/registry/plugins/install/callback`.

Security:
- Admin calls should be protected by `ADMIN_TOKEN` or `ADMIN_JWT_SECRET` shared between Core and Client Manager.

