# Setup: an isolated environment for the trestle library

`build_poam.py` needs the `compliance-trestle` Python package. **Never install it into the global
/ system Python** — always use an isolated environment. Pick a mechanism at runtime with this
ordered fallback, then remember which one you chose (you reuse it in build-poam.md).

## Decision tree

### 1. If `uv` is available → use it (preferred; nothing is persisted)

Check: `command -v uv`. If present, run the builder with an ephemeral, cached, isolated env — the
global site-packages is never touched:

```bash
uv run --with 'compliance-trestle>=3.0' python build_poam.py --input poam_input.json --output-dir out/
```

`build_poam.py` also carries a PEP 723 header, so `uv run build_poam.py …` works too. Use
`uv run --with 'compliance-trestle>=3.0' trestle …` for the validate step.

### 2. Else if `python3 -m venv` works → create a local venv

Check that venv creation actually works (some distros ship python without `ensurepip`):

```bash
python3 -m venv .venv-poam
```

If that succeeds, install trestle **into the venv only** and run the builder with the venv's python:

```bash
.venv-poam/bin/pip install -q 'compliance-trestle>=3.0'
.venv-poam/bin/python build_poam.py --input poam_input.json --output-dir out/
```

Keep `.venv-poam/` out of the deliverable (e.g. under the output dir or gitignored). Use
`.venv-poam/bin/trestle …` for the validate step.

### 3. Else → STOP and ask the user (do NOT install globally)

If `uv` is absent **and** `python3 -m venv` cannot create a working environment (missing
`ensurepip` / `python3-venv`, no network, no permissions), do **not** fall back to
`pip install compliance-trestle` into the global environment. Instead, tell the user plainly:

> I can't create an isolated Python environment, so I can't run the POA&M builder without polluting
> your global Python. Please enable one of the following, then I'll retry.

Offer these options:

- **Install uv** (simplest): `curl -LsSf https://astral.sh/uv/install.sh | sh`
  (or `pipx install uv`, or `brew install uv`).
- **Enable the venv module**: Debian/Ubuntu `sudo apt-get install python3-venv`; on RHEL/Fedora
  ensure the full `python3` (with `ensurepip`) is installed.
- **Use pipx** for the trestle CLI (validation only): `pipx install compliance-trestle`
  (note: running `build_poam.py` still needs uv or a venv).
- **Use a conda/mamba env**: `conda create -n poam python=3.11 && conda activate poam &&
  pip install compliance-trestle`.

Wait for the user to enable one, then re-run the decision tree.

## Verify the environment

Whichever path you used, confirm trestle imports before building:

```bash
# uv:   uv run --with 'compliance-trestle>=3.0' python -c "import trestle; from trestle.oscal import OSCAL_VERSION; print(OSCAL_VERSION)"
# venv: .venv-poam/bin/python -c "import trestle; from trestle.oscal import OSCAL_VERSION; print(OSCAL_VERSION)"
```
