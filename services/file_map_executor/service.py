"""Core service logic for file-map executor."""

import sys
import uuid
from typing import Dict, Any, List
from pathlib import Path


class FileMapExecutorService:
    """Executor service for file cleanup operations (dry_run=true only)."""

    def __init__(self):
        self.dry_run = True

    def execute(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute cleanup operation (dry_run=true only).

        This is a skeleton implementation that validates the request
        and returns a mock response. Actual file operations are handled
        by the existing cleanup_executor_api module.

        Args:
            request_data: Execute request payload

        Returns:
            Execute response with run_id, success_count, etc.
        """
        run_id = str(uuid.uuid4())

        plans = request_data.get('plans', [])

        return {
            'ok': True,
            'run_id': run_id,
            'dry_run': True,
            'success_count': len(plans),
            'succeeded': [plan.get('source', '') for plan in plans],
            'failed_count': 0,
            'failed': [],
            'error': None
        }

    def get_audit(self, run_id: str = None) -> Dict[str, Any]:
        """Get audit record for a run.

        Args:
            run_id: Run ID to query (optional)

        Returns:
            Audit information
        """
        return {
            'run_id': run_id,
            'audit_lines': [],
            'masked_paths': [],
            'error': None
        }

    def get_rollback(self, run_id: str = None) -> Dict[str, Any]:
        """Get rollback manifest for a run (read-only, no execution).

        Args:
            run_id: Run ID to query (optional)

        Returns:
            Rollback manifest
        """
        return {
            'run_id': run_id,
            'manifest': {},
            'rollback_status': 'pending',
            'error': None
        }

    def preflight(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate cleanup operation without execution (read-only).

        Checks if files exist and validates target paths.
        No actual file operations are performed.

        Args:
            request_data: Preflight request payload

        Returns:
            Preflight response with validation results
        """
        preflight_id = f"preflight-{uuid.uuid4()}"
        plans = request_data.get('plans', [])

        items = []
        ok_count = 0
        conflict_count = 0
        skipped_count = 0

        for plan in plans:
            source = plan.get('source', '')
            target = plan.get('target', '')

            # Simple validation: check source exists
            source_exists = Path(source).exists() if source else False

            if not source:
                items.append({
                    'source': source,
                    'target': target,
                    'status': 'invalid_path',
                    'reason': 'Source path is empty'
                })
                skipped_count += 1
            elif not source_exists:
                items.append({
                    'source': source,
                    'target': target,
                    'status': 'source_missing',
                    'reason': 'Source file does not exist'
                })
                skipped_count += 1
            else:
                # File exists, preflight OK
                items.append({
                    'source': source,
                    'target': target,
                    'status': 'ok',
                    'reason': ''
                })
                ok_count += 1

        return {
            'ok': True,
            'preflight_id': preflight_id,
            'dry_run': True,
            'total': len(plans),
            'ok_count': ok_count,
            'conflict_count': conflict_count,
            'skipped_count': skipped_count,
            'items': items,
            'error': None
        }
