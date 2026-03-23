# Agentic Agile Authoring

AI agent skills and modes for OSCAL-based compliance authoring — from NIST catalog customization through component definition to assessment result generation.

The OSCAL Compass project is hosted by the [Cloud Native Computing Foundation (CNCF)](https://cncf.io).

## Demo

https://github.com/user-attachments/assets/628ebb15-f9cc-4cef-88de-86f026bce499

The demo shows the full authoring lifecycle in Roo Code: tailoring a NIST SP 800-53 catalog, mapping controls to a Kubernetes component, and generating an assessment result — all through natural language.

## Getting Started

### 1. Prepare a workspace

Create a dedicated directory for your compliance authoring project and open it as your coding agent workspace.

```bash
mkdir my-compliance-workspace && cd my-compliance-workspace
```

### 2. Install

**Roo Code:**

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install
```

Then reload your workspace and switch to the **📑 Agentic Agile Authoring** mode in Roo Code.

> **Note:** Roo Code loads skills at startup. If you install after opening the workspace, reload it for the skills to take effect.

**Claude Code:**

```
/plugin marketplace add oscal-compass/agentic-agile-authoring
/plugin install agentic-agile-authoring@agentic-agile-authoring
```

### 3. Check Skills and MCP server

Confirm that the skills are loaded and the [trestle MCP server](https://github.com/oscal-compass/compliance-trestle-mcp) is enabled in your workspace. The agent relies on trestle MCP for all OSCAL operations.

### 4. Try compliance authoring

Follow along with the demo above. Type each prompt into Roo Code chat:

**Step 1 — Create a custom catalog**

Type in Roo Code:
```
Create regulatory controls for our organization, based on NIST SP 800-53 and limited to access control.
```
The agent prepares your regulatory document. Once done, it will ask if you want to customize the wording.

**Step 2 — Generate OSCAL catalog**

Type in Roo Code:
```
For now, proceed with the default wording. Please create the OSCAL JSON for this custom catalog.
```
`catalog.json` is created. Your controls are ready.

**Step 3 — Define a component (Kubernetes)**

Type in Roo Code:
```
Apply our organization's regulatory controls (catalogs/ac_controls_catalog) to Kubernetes. At this stage, please create the component definition.
```
The agent generates a human-readable implementation guide (Markdown + spreadsheet) per control, then produces the OSCAL `component-definition.json`. We recommend installing the [Rainbow CSV](https://marketplace.visualstudio.com/items?itemName=mechatroner.rainbow-csv) VS Code extension to review the spreadsheet output.

**Step 4 — Generate assessment results**

Type in Roo Code:
```
Using the component definition, create the assessment results.
```
Provide your security tool's scan output, and the agent generates an assessment posture. If no scan output is provided, a mock posture is created automatically.

---

## Skills

| Skill | Description |
|-------|-------------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results |
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) |

## Agent / Mode

A single agent **`agentic-agile-authoring`** covers the full OSCAL authoring lifecycle and delegates to the skills above.

| Platform | Agent definition | Skill location |
|----------|-----------------|----------------|
| **Claude Code** | `agents/claude/agentic-agile-authoring.md` | `skills/` |
| **Roo Code** | `agents-roo/agentic-agile-authoring/roo.yaml` | `.roo/skills[-agentic-agile-authoring]/` |

## Roo Code

### Auto install (recommended)

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install
```

Skills are installed to `.roo/skills-agentic-agile-authoring/` by default.
To install into the shared `.roo/skills/` directory instead (accessible to all modes):

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install --skills-scope common
```

### Uninstall

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring uninstall

# If installed with --skills-scope common:
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring uninstall --skills-scope common
```

### Manual install

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring download
```

Then follow the printed instructions to copy skills and import mode YAMLs into Roo Code.

### Install outputs

`.roo/skills-agentic-agile-authoring/` (or `.roo/skills/`) and `.roo/rules-*/` are created by the installer and gitignored.

## Claude Code

### Plugin install (once published)

```
/plugin marketplace add oscal-compass/agentic-agile-authoring
/plugin install agentic-agile-authoring@agentic-agile-authoring
```

### Local development

```bash
claude --plugin-dir ./
```

## Help

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring -h
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install -h
```

## License

Unless otherwise noted, files in this repository are licensed under the root LICENSE. Some skill directories include their own LICENSE.txt, which governs files in that directory.

---

We are a Cloud Native Computing Foundation sandbox project.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://www.cncf.io/wp-content/uploads/2022/07/cncf-white-logo.svg">
  <img src="https://www.cncf.io/wp-content/uploads/2022/07/cncf-color-bg.svg" width=300 />
</picture>

The Linux Foundation® (TLF) has registered trademarks and uses trademarks. For a list of TLF trademarks, see [Trademark Usage](https://www.linuxfoundation.org/legal/trademark-usage).
