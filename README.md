# DeployBot

DeployBot is a Python CLI for discovering devices on a local network and deploying sibling apps to them over SSH-compatible tooling.

## Commands

- `deploybot -help`: print the available features and commands.
- `deploybot discover [--ping-sweep]`: collect devices from known hosts, ARP data, and optional subnet probes.
- `deploybot list-apps`: find app folders next to this workspace.
- `deploybot deploy <app_name> <target> <destination> [--user USER] [--dry-run]`: deploy a sibling app.

## Gherkin tests

Run the feature suite with:

```bash
python3 tests/gherkin/run_features.py
```
