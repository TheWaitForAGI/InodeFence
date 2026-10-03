"""Pure comparison of observations; no contract or interestingness decisions."""

from inodefence.model import ChangeField, SnapshotPhase, StateChange, StateSnapshot


def compare_states(before: StateSnapshot, after: StateSnapshot) -> tuple[StateChange, ...]:
    """Compare only snapshots belonging to the same run and protected set."""
    if (
        before.sandbox_root != after.sandbox_root
        or before.protected_paths != after.protected_paths
        or before.phase != SnapshotPhase.BEFORE
        or after.phase != SnapshotPhase.AFTER
    ):
        raise ValueError("comparison requires before/after snapshots of the same run")
    old = {obj.path: obj for obj in before.objects}
    new = {obj.path: obj for obj in after.objects}
    changes = []
    for path in sorted(old.keys() | new.keys()):
        previous, current = old.get(path), new.get(path)
        if previous is None or current is None:
            fields = (ChangeField.EXISTENCE,)
        else:
            fields = tuple(
                field
                for field in ChangeField
                if field != ChangeField.EXISTENCE
                and getattr(previous, field.value) != getattr(current, field.value)
            )
        if fields:
            changes.append(StateChange(path, previous, current, fields))
    return tuple(changes)
