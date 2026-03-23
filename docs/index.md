# Agentic Agile Authoring

AI agent skills and modes for OSCAL-based compliance authoring — from NIST catalog customization through component definition to assessment result generation.

The OSCAL Compass project is hosted by the [Cloud Native Computing Foundation (CNCF)](https://cncf.io).

## Demo

<a href="https://github.com/oscal-compass/agentic-agile-authoring#demo">
  Watch the demo on GitHub
</a>

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

!!! note
    Roo Code loads skills at startup. If you install after opening the workspace, reload it for the skills to take effect.

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

```
Create regulatory controls for our organization, based on NIST SP 800-53 and limited to access control.
```

The agent prepares your regulatory document. Once done, it will ask if you want to customize the wording.

**Step 2 — Generate OSCAL catalog**

```
For now, proceed with the default wording. Please create the OSCAL JSON for this custom catalog.
```

`catalog.json` is created. Your controls are ready.

**Step 3 — Define a component (Kubernetes)**

```
Apply our organization's regulatory controls (catalogs/ac_controls_catalog) to Kubernetes. At this stage, please create the component definition.
```

The agent generates a human-readable implementation guide (Markdown + spreadsheet) per control, then produces the OSCAL `component-definition.json`.

**Step 4 — Generate assessment results**

```
Using the component definition, create the assessment results.
```

Provide your security tool's scan output, and the agent generates an assessment posture. If no scan output is provided, a mock posture is created automatically.

## Agent / Mode

A single agent **`agentic-agile-authoring`** covers the full OSCAL authoring lifecycle and delegates to the individual skills.

| Platform | Agent definition | Skill location |
|----------|-----------------|----------------|
| **Claude Code** | `agents/claude/agentic-agile-authoring.md` | `skills/` |
| **Roo Code** | `agents-roo/agentic-agile-authoring/roo.yaml` | `.roo/skills[-agentic-agile-authoring]/` |

## License

Unless otherwise noted, files in this repository are licensed under the Apache License 2.0. Some skill directories include their own LICENSE.txt, which governs files in that directory.

---

We are a Cloud Native Computing Foundation sandbox project.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://www.cncf.io/wp-content/uploads/2022/07/cncf-white-logo.svg">
  <img src="https://www.cncf.io/wp-content/uploads/2022/07/cncf-color-bg.svg" width=300 />
</picture>

The Linux Foundation® (TLF) has registered trademarks and uses trademarks. For a list of TLF trademarks, see [Trademark Usage](https://www.linuxfoundation.org/legal/trademark-usage).
