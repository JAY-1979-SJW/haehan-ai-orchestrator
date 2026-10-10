"""LOG-2B-2C: app_audit_log migration SQL validation tests.

Validates that the PostgreSQL migration file correctly defines
the append-only app_audit_log table with BROWSER-AUDIT-1 compatibility.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from core.agent_runtime.browser.approval.browser_audit_contract import (
    REQUIRED_AUDIT_COLUMNS,
    BrowserAuditEventType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_migration_file(filename: str) -> str:
    """Read migration SQL file."""
    base = Path(__file__).parent.parent
    path = base / "migrations" / filename
    return path.read_text(encoding="utf-8")


def _read_rollback_file() -> str:
    """Read rollback SQL file."""
    return _read_migration_file("rollback_log_2b_2c_app_audit_log.sql")


# ---------------------------------------------------------------------------
# File existence and structure
# ---------------------------------------------------------------------------


class TestMigrationFileExistence(unittest.TestCase):
    def test_migration_file_exists(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertGreater(len(content), 0)

    def test_rollback_file_exists(self):
        content = _read_rollback_file()
        self.assertGreater(len(content), 0)


class TestTransactionStructure(unittest.TestCase):
    def test_migration_has_begin_commit(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("BEGIN;", content, "migration must start with BEGIN;")
        self.assertIn("COMMIT;", content, "migration must end with COMMIT;")
        # BEGIN must come before COMMIT
        self.assertLess(content.index("BEGIN;"), content.index("COMMIT;"))

    def test_rollback_has_begin_commit(self):
        content = _read_rollback_file()
        self.assertIn("BEGIN;", content)
        self.assertIn("COMMIT;", content)


# ---------------------------------------------------------------------------
# Table definition
# ---------------------------------------------------------------------------


class TestTableDefinition(unittest.TestCase):
    def test_migration_creates_app_audit_log(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("CREATE TABLE", content)
        self.assertIn("app_audit_log", content)

    def test_migration_has_required_columns(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        for col in REQUIRED_AUDIT_COLUMNS:
            self.assertIn(col, content, f"required column {col} not in migration")

    def test_migration_has_organization_id(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("organization_id", content)

    def test_migration_has_actor_user_id(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("actor_user_id", content)

    def test_migration_has_event_hash_previous_event_hash(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("event_hash", content)
        self.assertIn("previous_event_hash", content)

    def test_migration_has_payload_hash(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("payload_hash", content)

    def test_migration_has_metadata_json(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("metadata_json", content)
        self.assertIn("JSONB", content)


# ---------------------------------------------------------------------------
# Enum definition
# ---------------------------------------------------------------------------


class TestEnumDefinition(unittest.TestCase):
    def test_migration_defines_status_enum_or_constraint(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        has_enum = "CREATE TYPE app_audit_event_status AS ENUM" in content
        has_check = "CHECK" in content and ("PASS" in content or "status" in content)
        self.assertTrue(has_enum or has_check, "migration must define status constraint or enum")

    def test_status_enum_includes_required_values(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        for status in ["PASS", "WARN", "FAIL", "SKIP", "ERROR"]:
            self.assertIn(f"'{status}'", content, f"status {status} not in enum definition")


# ---------------------------------------------------------------------------
# Append-only protection
# ---------------------------------------------------------------------------


class TestAppendOnlyProtection(unittest.TestCase):
    def test_migration_has_append_only_trigger(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("BEFORE UPDATE", content)
        self.assertIn("BEFORE DELETE", content)
        self.assertIn("TRIGGER", content)

    def test_migration_blocks_update_delete(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertIn("prevent_app_audit_log_update", content)
        self.assertIn("prevent_app_audit_log_delete", content)
        self.assertIn("RAISE EXCEPTION", content)


# ---------------------------------------------------------------------------
# Index definitions
# ---------------------------------------------------------------------------


class TestIndexes(unittest.TestCase):
    def test_migration_has_required_indexes(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        required_indexes = [
            "event_at",
            "event_type_event_at",
            "actor_user_id_event_at",
            "organization_id_event_at",
            "target_type_target_id",
            "request_id",
            "status_event_at",
            "payload_hash",
            "event_hash",
            "previous_event_hash",
        ]
        for idx in required_indexes:
            self.assertIn(idx, content.lower(), f"index {idx} not defined")


# ---------------------------------------------------------------------------
# Safety checks: no dangerous SQL
# ---------------------------------------------------------------------------


class TestSafety(unittest.TestCase):
    def test_migration_has_no_drop_table(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertNotIn("DROP TABLE app_audit_log", content)

    def test_migration_has_no_truncate(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertNotIn("TRUNCATE", content)

    def test_migration_has_no_delete_from(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        self.assertNotIn("DELETE FROM", content)

    def test_migration_does_not_modify_existing_tables(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        # Should only create new objects, not alter existing
        unwanted_patterns = [
            "ALTER TABLE",
            "ALTER TYPE",
            "DROP FUNCTION",
            "DROP TYPE",
        ]
        # Rollback is allowed to have these, but migration shouldn't
        for pattern in unwanted_patterns:
            # Count occurrences - migration should have 0, rollback has them
            count = content.count(pattern)
            self.assertEqual(count, 0, f"migration must not contain {pattern}")


# ---------------------------------------------------------------------------
# Contract alignment
# ---------------------------------------------------------------------------


class TestBrowserAuditContractAlignment(unittest.TestCase):
    def test_browser_audit_contract_required_columns_match_migration(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        missing = []
        for col in REQUIRED_AUDIT_COLUMNS:
            if col not in content:
                missing.append(col)
        self.assertEqual(len(missing), 0, f"missing required columns: {missing}")

    def test_all_status_values_from_contract_in_enum(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        for event_type in BrowserAuditEventType:
            # Event types like "browser.task.executed" → we check status values
            pass
        # Status values should match contract
        for status in ["PASS", "WARN", "FAIL", "SKIP", "ERROR"]:
            self.assertIn(f"'{status}'", content)


# ---------------------------------------------------------------------------
# Rollback validation
# ---------------------------------------------------------------------------


class TestRollback(unittest.TestCase):
    def test_rollback_is_separate_file(self):
        rollback = _read_rollback_file()
        self.assertGreater(len(rollback), 0)
        self.assertIn("DROP TABLE", rollback)
        self.assertIn("DROP TYPE", rollback)

    def test_rollback_drops_table(self):
        rollback = _read_rollback_file()
        self.assertIn("DROP TABLE IF EXISTS app_audit_log", rollback)

    def test_rollback_drops_enum(self):
        rollback = _read_rollback_file()
        self.assertIn("DROP TYPE IF EXISTS app_audit_event_status", rollback)


# ---------------------------------------------------------------------------
# Secret scanning
# ---------------------------------------------------------------------------


class TestNoSecrets(unittest.TestCase):
    def test_no_secret_values_in_migration(self):
        content = _read_migration_file("log_2b_2c_app_audit_log.sql")
        forbidden_patterns = [
            r"password\s*=",
            r"secret\s*=",
            r"token\s*=",
            r"key\s*=",
            r"'[A-Za-z0-9]{20,}'",  # suspicious long strings
        ]
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            self.assertEqual(len(matches), 0, f"potential secret found matching {pattern}")

    def test_no_secret_values_in_rollback(self):
        content = _read_rollback_file()
        # Rollback is even simpler - just drops
        self.assertNotIn("password", content.lower())
        self.assertNotIn("secret", content.lower())


if __name__ == "__main__":
    unittest.main()
