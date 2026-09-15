# KLTN Research Workspace

This Git repository publishes only the reproducibility package under
[`artifact/`](artifact/).

The local `cowork/` directory contains manuscript sources, authoring notes,
local models, and working files. It is intentionally ignored by Git and is not
part of the public repository.

See [`artifact/README.md`](artifact/README.md) for data provenance, environment
setup, verification, replay, and testing instructions.

## Maintainer synchronization

Files required in both areas are versioned under `artifact/`. Check whether the
ignored cowork copy is current:

~~~powershell
python artifact/tools/reproduction/sync_cowork_mirror.py --check
~~~

Synchronize missing or changed shared files from `artifact/` to `cowork/`:

~~~powershell
python artifact/tools/reproduction/sync_cowork_mirror.py --sync
~~~

The synchronizer never deletes cowork-only files.
