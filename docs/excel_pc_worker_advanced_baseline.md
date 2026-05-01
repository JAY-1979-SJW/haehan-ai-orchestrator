# Excel PC Advanced Worker - Baseline Specification (Stage 10, EXCEL-PC-8B)

**Date:** 2026-05-02  
**Status:** Baseline Locked  
**Testing:** All 309 tests passing (284 Excel-specific + 25 framework tests)

## Overview

The Excel PC Advanced Worker is a comprehensive Excel automation system implementing 8 progressive enhancement stages (EXCEL-PC-1 through EXCEL-PC-8B) with strong safety controls, approval-based workflows, and industry-specific business logic.

**Key Principle:** Protect original files through copy-based workflows and approval gating. Original Save requires backup + hash verification + document protection checks.

---

## Implementation Stages (1-10)

### Stage 1: Basic Operations (EXCEL-PC-1)
- Read/write cells, workbooks via COM
- POC workflows with dry-run capability
- File path validation
- Excel app health checks

### Stage 2: Modular Workflows (EXCEL-PC-2)
- Header detection and mapping
- Row/column operations with header-aware matching
- Style copying (format propagation)
- Copy-based save protection

### Stage 3: Change Planning (EXCEL-PC-3)
- Operation schema definition (update cell, insert row/column, write formula)
- Change plan creation with dry-run preview
- Operation normalization
- Conflict avoidance

### Stage 4: Batch Execution & Validation (EXCEL-PC-4A/4B)
- Sequential operation execution
- Logging and change tracking
- Formula validation (consistency, error detection)
- Data quality validation (duplicates, missing values, type consistency)

### Stage 5: Review & Reporting (EXCEL-PC-5A/5B)
- Multi-sheet structure analysis
- Automatic review sheet generation
- Change summary tables
- Validation issue reporting

### Stage 6: PDF & Printing (EXCEL-PC-6A/6B)
- Active sheet/workbook PDF export
- Selective sheet export
- Print area management
- Page setup controls

### Stage 7: Industry Packs (EXCEL-PC-7A/7B)
- **Construction Estimate Pack:**
  - Auto-detect item/spec/qty/price/amount columns
  - Validate amount formulas (qty × unit price)
  - Detect price anomalies, missing quantities, duplicate items
  
- **Settlement Review Pack:**
  - Claim vs. actual discrepancy detection
  - Threshold-based variance flagging
  
- **Material Price Check Pack:**
  - Price variation analysis
  - Consistency validation
  - Outlier detection

### Stage 8: External Data Integration (EXCEL-PC-7B)
- Material DB adapter (record matching, unmatched detection)
- CAD takeoff adapter (quantity reconciliation)
- Bid analysis adapter (price competitiveness evaluation)
- No DB writes, no external API calls (preparation only)

### Stage 9: Original Save with Backup (EXCEL-PC-8A)
- Approval-based original file save
- Automatic backup creation with timestamps
- Change plan hash verification
- Document protection checking
- Backup cleanup (max 3 per file)

### Stage 10: Baseline Lock (EXCEL-PC-8B)
- Comprehensive regression testing
- Baseline documentation
- Action inventory
- Known limitations catalog

---

## Action Registry (13 Excel Actions + Pack Actions)

### Core Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.run_poc | LOW | No | No | Yes |
| excel.read_cell | LOW | No | No | Yes |
| excel.write_cell | MEDIUM | Yes | No | No |
| excel.save_as | MEDIUM | Yes | Yes | No |
| excel.probe_active_workbook | LOW | No | No | Yes |

### Analysis Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.analyze_workbook | LOW | No | No | Yes |
| excel.analyze_active_sheet_structure | LOW | No | No | Yes |

### Planning & Execution Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.plan_changes | LOW | No | No | Yes |
| excel.apply_change_plan_copy | MEDIUM | Yes | Yes | No |

### Workflow Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.update_cell_by_header_copy | MEDIUM | Yes | Yes | No |
| excel.insert_row_by_header_copy | MEDIUM | Yes | Yes | No |
| excel.insert_column_by_header_copy | MEDIUM | Yes | Yes | No |
| excel.write_formula_by_header_copy | MEDIUM | Yes | Yes | No |

### Validation Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.validate_active_workbook | LOW | No | No | Yes |
| excel.validate_change_result | LOW | No | No | Yes |
| excel.validate_data_quality | LOW | No | No | Yes |
| excel.validate_formulas | LOW | No | No | Yes |

### Reporting Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.create_review_summary_sheet_copy | MEDIUM | Yes | Yes | No |
| excel.generate_analysis_report | LOW | No | No | Yes |

### Export Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.export_pdf_copy | MEDIUM | Yes | Yes | No |

### Pack Actions
| Action | Risk | Approval | SaveAs | ReadOnly |
|--------|------|----------|--------|----------|
| excel.pack.review_estimate_copy | MEDIUM | Yes | Yes | No |
| excel.pack.review_settlement_copy | MEDIUM | Yes | Yes | No |
| excel.pack.check_material_prices_copy | MEDIUM | Yes | Yes | No |

### Original Save (Future)
| Action | Risk | Approval | Backup | ReadOnly |
|--------|------|----------|--------|----------|
| excel.save_original_with_backup | HIGH | Yes | Yes | No |

---

## Approval Policies

### Write Operations (MEDIUM Risk)
- **Requirement:** Valid approval_token (non-empty string)
- **Scope:** Cell/row/column updates, formula writes, sheet additions, PDF exports
- **Protection:** SaveCopyAs enforced (original never overwritten)

### Original File Save (HIGH Risk)
- **Requirements:**
  1. Approval token with change hash verification
  2. Automatic backup creation before save
  3. Document protection checks:
     - No read-only files
     - No structure-protected workbooks
     - No shared documents
  4. Change plan hash must match token hash
  5. Backup integrity verification

- **STOP Conditions:** Any failure in above steps cancels operation

### No Approval Needed
- Read-only operations (analysis, validation, plan preview)
- Workbook closing (separate close-workflow authorization)

---

## Safety Controls

### File Protection
1. **Copy-based Save:** All write operations save to new file (SaveCopyAs)
2. **Original Preservation:** Original file never modified unless explicit approval + backup
3. **Backup Management:** Automatic backups with timestamp, keep last 3
4. **Read-only Enforcement:** All read-only workbooks block writes

### Document State Checks
- ProtectStructure: Blocks original save
- ProtectWindows: Blocks original save
- ReadOnly: Blocks all write operations
- MultiUserEditing (shared): Blocks original save

### Change Validation
- Hash-based change verification (SHA256 first 16 chars)
- Operation logging with status tracking
- Pre-save dry-run capability
- Formula consistency validation

---

## Forbidden Operations

1. **Save original file without approval + backup**
2. **Modify COM object properties without isolated workbook**
3. **Bypass document protection checks**
4. **Delete backup files manually**
5. **Call external APIs without adapter pattern**
6. **Modify shared documents**
7. **Access credentials via environment variables in production**

---

## Known Limitations

1. **No Real-time Collaboration:** Multi-user editing blocked
2. **No Database Connection:** Integration adapters prepare schema only
3. **No CAD Direct Modification:** CAD read-only (future: structured export/import)
4. **Limited Format Support:** Excel 2016+ (.xlsx), no legacy formats (.xls)
5. **No Macro Support:** VBA/macros not preserved in SaveCopyAs workflows
6. **String-based Matching Only:** Material/CAD/Bid matching uses simple string similarity (future: SQL/API)
7. **English Error Messages Only:** No localization (future consideration)
8. **Batch Size Limits:** No performance testing for >10K row operations

---

## Testing Baseline

**Total Coverage:** 309 tests passing

### Test Distribution
- Excel module tests: 284 tests
  - Basic operations: 15 tests
  - Workflows: 20 tests
  - Validation: 30 tests
  - Analysis: 25 tests
  - Packs: 16 tests
  - Integrations: 16 tests
  - Original save policy: 25 tests
  - (Plus additional module tests: ~137)

- Framework tests: 25 tests
  - Task executor: 21 tests
  - Action registry: 4 tests

### Test Execution
```bash
python -m py_compile agent/excel/*.py agent/excel/packs/*.py agent/excel/integrations/*.py
python -m pytest agent/tests/test_excel_*.py agent/tests/test_task_executor_unit.py agent/tests/test_action_registry_unit.py -q
```

---

## Next Steps (Future Stages)

### EXCEL-PC-9: UI Integration
- Web dashboard for change planning
- Approval flow UI
- Real-time execution monitoring
- Backup browser

### EXCEL-PC-10: Database & CAD
- Material DB query adapter
- CAD API integration
- Credential management
- Audit logging

### EXCEL-PC-11: Performance & Scale
- Batch optimization for 10K+ rows
- Memory profiling
- Cache strategies
- Concurrent workbook handling

### EXCEL-PC-12: Enterprise Features
- Multi-user approval workflows
- Audit trail with signatures
- Compliance reporting
- Data governance

---

## Architecture Principles

1. **Modular by Default:** Each stage builds on previous, no breaking changes
2. **Safety First:** Approval gates protect critical operations
3. **Copy-First:** Write operations never touch originals
4. **Test Everything:** 100% path coverage for safety-critical features
5. **Document Explicitly:** This baseline is the source of truth

---

## Maintenance

- **Baseline Review Interval:** Quarterly or per major feature
- **Deprecation Policy:** 6-month notice before removing stable APIs
- **Breaking Changes:** Require major version bump and 3-month transition
- **Security Patches:** Applied immediately with hotfix releases

---

**Baseline Locked:** 2026-05-02  
**Next Review:** 2026-08-02  
**Maintainer:** AI Orchestrator Team
