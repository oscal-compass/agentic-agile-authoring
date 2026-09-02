# =============================================================================
# demos/pdf-to-catalog-and-mapping — PDF → OSCAL Catalog → Mapping Collection
#
# Targets
#   (default)  print help
#   status     show which skills are installed and whether outputs exist
#   catalog    run compliance-catalog skill: 800-171 PDF → catalog.json
#   mapping    run compliance-mapping skill: 800-171 ↔ 800-53 → mapping_collection.json + report.html
#   all        catalog, then mapping
#   clean      restore repo-fresh state: remove output/ and .env
# =============================================================================

.PHONY: help status catalog mapping all clean

# ---------------------------------------------------------------------------
# Paths — works whether make is run from repo root or from demos/pdf-to-catalog-and-mapping/
# ---------------------------------------------------------------------------
REPO_ROOT   ?= ../..
DEMO_DIR    := $(REPO_ROOT)/demos/pdf-to-catalog-and-mapping
RESOURCES   := $(REPO_ROOT)/demos/resources

PDF_INPUT   := $(RESOURCES)/pdfs/NIST.SP.800-171r3.pdf
TARGET_CAT  := $(RESOURCES)/oscal/NIST_SP-800-53_rev5_HIGH-baseline-resolved-profile_catalog.json

CATALOG_OUT := $(DEMO_DIR)/output/800-171-catalog
MAPPING_OUT := $(DEMO_DIR)/output/800-171-to-800-53
SOURCE_CAT  := $(CATALOG_OUT)/catalog.json

ENV_FILE    := $(DEMO_DIR)/.env

# ---------------------------------------------------------------------------
# Timeouts — hard kill if the agent has not finished by this many seconds.
#
# Catalog  basis: the compliance-catalog regression harness uses 1800 s for
#          small PDFs; SP 800-171r3 is 1.6 MB and the happy path is ~10-20 min,
#          but the fix loop can add 5-10 min per iteration — 2700 s (45 min)
#          gives headroom for 2-3 iterations without false-killing a slow run.
#
# Mapping  basis: the mapping pipeline takes ~5-15 min for this catalog pair
#          (~110 × 188 controls); 1800 s (30 min) covers judge-chunk retries.
#
# Override on the command line if needed:
#   make catalog CATALOG_TIMEOUT=3600
#   make mapping MAPPING_TIMEOUT=2400
# ---------------------------------------------------------------------------
CATALOG_TIMEOUT ?= 2700
MAPPING_TIMEOUT ?= 1800

# ---------------------------------------------------------------------------
# Default target — help
# ---------------------------------------------------------------------------
.DEFAULT_GOAL := help

help:
	@echo ""
	@echo "  pdf-to-catalog-and-mapping demo"
	@echo ""
	@printf "  \033[36m%-12s\033[0m %s\n" "status"  "Show skill install status and output state"
	@printf "  \033[36m%-12s\033[0m %s\n" "catalog" "Scenario 1: 800-171 PDF → catalog.json  (timeout $(CATALOG_TIMEOUT)s)"
	@printf "  \033[36m%-12s\033[0m %s\n" "mapping" "Scenario 2: 800-171 ↔ 800-53 → mapping_collection.json + report.html  (timeout $(MAPPING_TIMEOUT)s)"
	@printf "  \033[36m%-12s\033[0m %s\n" "all"     "Run catalog then mapping"
	@printf "  \033[36m%-12s\033[0m %s\n" "clean"   "Restore repo-fresh state: remove output/ and .env"
	@echo ""
	@echo "  Harness and API key are prompted on first run and saved to .env."
	@echo "  Override timeouts: make catalog CATALOG_TIMEOUT=3600"
	@echo ""

# ---------------------------------------------------------------------------
# status — show skill install state and output artifacts
# ---------------------------------------------------------------------------
status:
	@echo ""
	@echo "=== Skills ==="
	@_check_skill() { \
	  SKILL=$$1; LABEL=$$2; \
	  FOUND=""; \
	  for DIR in \
	    "$(REPO_ROOT)/.bob/skills/$$SKILL" \
	    "$(REPO_ROOT)/.claude/skills/$$SKILL" \
	    "$(REPO_ROOT)/.agents/skills/$$SKILL" \
	    "$$HOME/.bob/skills/$$SKILL" \
	    "$$HOME/.claude/skills/$$SKILL" \
	    "$$HOME/.agents/skills/$$SKILL"; do \
	    if [ -f "$$DIR/SKILL.md" ]; then \
	      VER=$$(grep '^version:' "$$DIR/../apm.yml" 2>/dev/null | head -1 | sed 's/.*version:[[:space:]]*//' | tr -d '"' || echo ""); \
	      WHERE=$$(echo "$$DIR" | sed "s|$$HOME|~|g" | sed "s|$$(pwd)/||g"); \
	      FOUND="$$FOUND  ✓ $$WHERE$$([ -n "$$VER" ] && echo " (v$$VER)" || echo "")\n"; \
	    fi; \
	  done; \
	  if [ -n "$$FOUND" ]; then \
	    printf "  \033[32m%-30s installed\033[0m\n" "$$LABEL"; \
	    printf "$$FOUND" | sed 's/^/    /'; \
	  else \
	    printf "  \033[33m%-30s NOT installed\033[0m\n" "$$LABEL"; \
	    echo "    run: uvx --from 'git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools' \\"; \
	    echo "           compliance-authoring-skills install --demo pdf-to-catalog-and-mapping --target bob"; \
	  fi; \
	}; \
	_check_skill compliance-catalog "compliance-catalog"; \
	_check_skill compliance-mapping "compliance-mapping"
	@echo ""
	@echo "=== Outputs ==="
	@_show_output() { \
	  FILE=$$1; LABEL=$$2; \
	  if [ -f "$$FILE" ]; then \
	    SIZE=$$(du -sh "$$FILE" 2>/dev/null | cut -f1); \
	    MTIME=$$(date -r "$$FILE" '+%Y-%m-%d %H:%M' 2>/dev/null || stat -c '%y' "$$FILE" 2>/dev/null | cut -d' ' -f1,2 | cut -c1-16); \
	    printf "  \033[32m✓ %-40s\033[0m %s  %s\n" "$$LABEL" "$$SIZE" "$$MTIME"; \
	  else \
	    printf "  \033[33m✗ %-40s\033[0m not yet generated\n" "$$LABEL"; \
	  fi; \
	}; \
	_show_output "$(CATALOG_OUT)/catalog.json"              "output/800-171-catalog/catalog.json"; \
	_show_output "$(MAPPING_OUT)/mapping_collection.json"   "output/800-171-to-800-53/mapping_collection.json"; \
	_show_output "$(MAPPING_OUT)/report.html"               "output/800-171-to-800-53/report.html"
	@echo ""
	@echo "=== Config ==="
	@if [ -f "$(ENV_FILE)" ]; then \
	  HARNESS=$$(grep '^HARNESS=' "$(ENV_FILE)" | cut -d= -f2); \
	  printf "  \033[32m✓ .env\033[0m  harness=%s\n" "$${HARNESS:-not set}"; \
	else \
	  printf "  \033[33m✗ .env\033[0m  not configured — run make catalog to be prompted\n"; \
	fi
	@echo ""

# ---------------------------------------------------------------------------
# catalog — Scenario 1: PDF → OSCAL Catalog
# ---------------------------------------------------------------------------
catalog:
	@ENV_FILE="$(ENV_FILE)"; \
	PDF_INPUT="$(PDF_INPUT)"; \
	CATALOG_OUT="$(CATALOG_OUT)"; \
	TIMEOUT=$(CATALOG_TIMEOUT); \
	\
	[ -f "$$ENV_FILE" ] && . "$$ENV_FILE"; \
	\
	if [ -z "$$HARNESS" ]; then \
	  echo ""; \
	  echo "Select harness:"; \
	  echo "  1) bob      (IBM Bob Shell)"; \
	  echo "  2) claude   (Claude Code)"; \
	  echo "  3) opencode (OpenCode)"; \
	  printf "Choice [1]: "; \
	  read CHOICE; \
	  CHOICE=$${CHOICE:-1}; \
	  case "$$CHOICE" in \
	    1|bob)      HARNESS=bob ;; \
	    2|claude)   HARNESS=claude ;; \
	    3|opencode) HARNESS=opencode ;; \
	    *) echo "Invalid choice. Aborting."; exit 1 ;; \
	  esac; \
	  echo ""; \
	fi; \
	\
	case "$$HARNESS" in \
	  bob)      KEY_VAR=BOB_API_KEY ;; \
	  claude)   KEY_VAR=ANTHROPIC_API_KEY ;; \
	  opencode) KEY_VAR=OPENAI_API_KEY ;; \
	  *) echo "Unknown harness: $$HARNESS"; exit 1 ;; \
	esac; \
	\
	eval "KEY_VAL=\$${$$KEY_VAR}"; \
	if [ -z "$$KEY_VAL" ]; then \
	  printf "Enter $$KEY_VAR: "; \
	  read -rs KEY_VAL; \
	  echo ""; \
	  [ -z "$$KEY_VAL" ] && echo "No key entered. Aborting." && exit 1; \
	fi; \
	\
	printf "HARNESS=%s\n%s=%s\n" "$$HARNESS" "$$KEY_VAR" "$$KEY_VAL" > "$$ENV_FILE"; \
	export "$$KEY_VAR=$$KEY_VAL"; \
	\
	case "$$HARNESS" in \
	  bob)      CMD="bob run --trust --accept-license --format stream-json" ;; \
	  claude)   CMD="claude --dangerously-skip-permissions -p" ;; \
	  opencode) CMD="opencode run -p" ;; \
	esac; \
	CLI=$$(echo "$$CMD" | cut -d' ' -f1); \
	if ! command -v "$$CLI" >/dev/null 2>&1; then \
	  echo "ERROR: '$$CLI' not found on PATH. Install the $$HARNESS CLI and re-run."; \
	  exit 1; \
	fi; \
	\
	echo ""; \
	echo "=== Scenario 1: Building OSCAL Catalog from PDF ==="; \
	echo "  task    : Convert NIST SP 800-171r3 PDF → validated OSCAL catalog.json"; \
	echo "  skill   : compliance-catalog  (skills/compliance-catalog/SKILL.md)"; \
	echo "  harness : $$HARNESS"; \
	echo "  input   : $$PDF_INPUT"; \
	echo "  output  : $$CATALOG_OUT/"; \
	echo ""; \
	mkdir -p "$$CATALOG_OUT"; \
	PROMPT="Follow \`skills/compliance-catalog/SKILL.md\` to build an OSCAL Catalog from a PDF. - input_pdf: $$PDF_INPUT - output_dir: $$CATALOG_OUT"; \
	echo "  command : $$CMD \\"; \
	echo "              \"$$PROMPT\""; \
	echo ""; \
	sh "$(DEMO_DIR)/run_agent.sh" \
	  catalog "$$CATALOG_OUT/agent.jsonl" "$$TIMEOUT" "-f $$CATALOG_OUT/catalog.json" \
	  -- $$CMD "$$PROMPT" || exit 1; \
	echo "  OK: $$CATALOG_OUT/catalog.json written."

# ---------------------------------------------------------------------------
# mapping — Scenario 2: Catalog × Catalog → Mapping Collection
# ---------------------------------------------------------------------------
mapping:
	@ENV_FILE="$(ENV_FILE)"; \
	SOURCE_CAT="$(SOURCE_CAT)"; \
	TARGET_CAT="$(TARGET_CAT)"; \
	MAPPING_OUT="$(MAPPING_OUT)"; \
	TIMEOUT=$(MAPPING_TIMEOUT); \
	\
	if [ ! -f "$$SOURCE_CAT" ]; then \
	  echo "ERROR: $$SOURCE_CAT not found. Run 'make catalog' first."; \
	  exit 1; \
	fi; \
	\
	[ -f "$$ENV_FILE" ] && . "$$ENV_FILE"; \
	\
	if [ -z "$$HARNESS" ]; then \
	  echo ""; \
	  echo "Select harness:"; \
	  echo "  1) bob      (IBM Bob Shell)"; \
	  echo "  2) claude   (Claude Code)"; \
	  echo "  3) opencode (OpenCode)"; \
	  printf "Choice [1]: "; \
	  read CHOICE; \
	  CHOICE=$${CHOICE:-1}; \
	  case "$$CHOICE" in \
	    1|bob)      HARNESS=bob ;; \
	    2|claude)   HARNESS=claude ;; \
	    3|opencode) HARNESS=opencode ;; \
	    *) echo "Invalid choice. Aborting."; exit 1 ;; \
	  esac; \
	  echo ""; \
	fi; \
	\
	case "$$HARNESS" in \
	  bob)      KEY_VAR=BOB_API_KEY ;; \
	  claude)   KEY_VAR=ANTHROPIC_API_KEY ;; \
	  opencode) KEY_VAR=OPENAI_API_KEY ;; \
	  *) echo "Unknown harness: $$HARNESS"; exit 1 ;; \
	esac; \
	\
	eval "KEY_VAL=\$${$$KEY_VAR}"; \
	if [ -z "$$KEY_VAL" ]; then \
	  printf "Enter $$KEY_VAR: "; \
	  read -rs KEY_VAL; \
	  echo ""; \
	  [ -z "$$KEY_VAL" ] && echo "No key entered. Aborting." && exit 1; \
	fi; \
	\
	printf "HARNESS=%s\n%s=%s\n" "$$HARNESS" "$$KEY_VAR" "$$KEY_VAL" > "$$ENV_FILE"; \
	export "$$KEY_VAR=$$KEY_VAL"; \
	\
	case "$$HARNESS" in \
	  bob)      CMD="bob run --trust --accept-license --format stream-json" ;; \
	  claude)   CMD="claude --dangerously-skip-permissions -p" ;; \
	  opencode) CMD="opencode run -p" ;; \
	esac; \
	CLI=$$(echo "$$CMD" | cut -d' ' -f1); \
	if ! command -v "$$CLI" >/dev/null 2>&1; then \
	  echo "ERROR: '$$CLI' not found on PATH. Install the $$HARNESS CLI and re-run."; \
	  exit 1; \
	fi; \
	\
	echo ""; \
	echo "=== Scenario 2: Mapping NIST SP 800-171 → NIST SP 800-53 ==="; \
	echo "  task    : Map 800-171 controls against 800-53 High baseline → mapping_collection.json + report.html"; \
	echo "  skill   : compliance-mapping  (skills/compliance-mapping/SKILL.md)"; \
	echo "  harness : $$HARNESS"; \
	echo "  source  : $$SOURCE_CAT"; \
	echo "  target  : $$TARGET_CAT"; \
	echo "  output  : $$MAPPING_OUT/"; \
	echo ""; \
	mkdir -p "$$MAPPING_OUT"; \
	PROMPT="Follow \`skills/compliance-mapping/SKILL.md\` to map two OSCAL Catalogs. - source_catalog: $$SOURCE_CAT - target_catalog: $$TARGET_CAT - output_dir: $$MAPPING_OUT"; \
	echo "  command : $$CMD \\"; \
	echo "              \"$$PROMPT\""; \
	echo ""; \
	sh "$(DEMO_DIR)/run_agent.sh" \
	  mapping "$$MAPPING_OUT/agent.jsonl" "$$TIMEOUT" \
	  "-f $$MAPPING_OUT/mapping_collection.json -a -f $$MAPPING_OUT/report.html" \
	  -- $$CMD "$$PROMPT" || exit 1; \
	echo "  OK: mapping_collection.json and report.html written."; \
	echo "  Open: $$MAPPING_OUT/report.html"

# ---------------------------------------------------------------------------
# all — catalog then mapping
# ---------------------------------------------------------------------------
all: catalog mapping

# ---------------------------------------------------------------------------
# clean — remove generated output
# ---------------------------------------------------------------------------
clean:
	@rm -rf $(DEMO_DIR)/output
	@rm -f $(ENV_FILE)
	@echo "Clean. (output/ and .env removed — repo-fresh state.)"
