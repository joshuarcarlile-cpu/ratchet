# ratchet marketplace

Self-hosted Claude Code plugin marketplace for [`ratchet`](plugin/README.md) — a workflow-discipline plugin: plan-first, minimal-code, and auto-generated regression tests/scripts for whatever project it's installed in.

## Install

```
/plugin marketplace add <owner>/ratchet
/plugin install ratchet
```

## Local, before publishing

```bash
claude --plugin-dir ./plugin
```

or, to rehearse the real marketplace flow without pushing anywhere:

```
/plugin marketplace add /absolute/path/to/ratchet
/plugin install ratchet
```

See `plugin/README.md` for what the plugin actually does.
