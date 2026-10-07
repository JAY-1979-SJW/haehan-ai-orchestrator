from pathlib import Path

import yaml

_POLICY_PATH = Path(__file__).resolve().parents[2] / "policies" / "default_policy.yaml"


def load_policy(path: str | None = None) -> dict:
    target = path or _POLICY_PATH
    with Path(target).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_risk_level_for_action(action_type: str, policy: dict) -> str | None:
    for level, cfg in policy.get("risk_levels", {}).items():
        if action_type in cfg.get("actions", []):
            return level
    return None


def is_path_allowed(path: str, policy: dict) -> bool:
    blocked = policy.get("blocked_paths", [])
    allowed = policy.get("allowed_paths", [])
    for bp in blocked:
        if path.startswith(bp):
            return False
    for ap in allowed:
        if path.startswith(ap):
            return True
    return False


def is_command_blocked(command: str, policy: dict) -> bool:
    for bc in policy.get("blocked_commands", []):
        if bc.lower() in command.lower():
            return True
    return False


def is_command_allowed(command: str, policy: dict) -> bool:
    for ac in policy.get("allowed_commands", []):
        if command.strip().startswith(ac):
            return True
    return False
