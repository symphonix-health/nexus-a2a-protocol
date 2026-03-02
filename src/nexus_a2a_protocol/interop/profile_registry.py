"""In-memory profile registry with deterministic SemVer resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProfileRecord:
    profile_id: str
    version: str
    adapter_endpoint: str
    constraints: dict[str, Any] = field(default_factory=dict)


class InMemoryProfileRegistry:
    """Registry for profile -> adapter endpoint resolution.

    Resolution order:
    1) exact match for requested profile (including optional @version)
    2) fallback to highest compatible version within acceptable profiles
    """

    def __init__(self) -> None:
        self._records: list[ProfileRecord] = []

    def list_profiles(self) -> list[ProfileRecord]:
        return list(self._records)

    def create_profile(self, record: ProfileRecord) -> None:
        existing = self._find(record.profile_id, record.version)
        if existing is not None:
            raise ValueError("profile/version already exists")
        self._records.append(record)

    def update_profile(
        self,
        profile_id: str,
        version: str,
        *,
        adapter_endpoint: str | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> ProfileRecord:
        record = self._find(profile_id, version)
        if record is None:
            raise KeyError("profile/version not found")
        if adapter_endpoint is not None:
            record.adapter_endpoint = adapter_endpoint
        if constraints is not None:
            record.constraints = dict(constraints)
        return record

    def delete_profile(self, profile_id: str, version: str) -> None:
        before = len(self._records)
        self._records = [
            entry
            for entry in self._records
            if not (entry.profile_id == profile_id and entry.version == version)
        ]
        if len(self._records) == before:
            raise KeyError("profile/version not found")

    def resolve(
        self,
        *,
        requested_profile: str,
        acceptable_profiles: list[dict[str, str]] | None = None,
    ) -> ProfileRecord | None:
        profile_id, requested_version = _split_requested_profile(requested_profile)

        if requested_version:
            exact = self._find(profile_id, requested_version)
            if exact is not None:
                return exact

        candidates = [entry for entry in self._records if entry.profile_id == profile_id]
        if candidates:
            return max(candidates, key=lambda e: _parse_semver(e.version))

        acceptable_profiles = acceptable_profiles or []
        all_acceptable: list[ProfileRecord] = []
        for acceptable in acceptable_profiles:
            acceptable_id = acceptable.get("profileId", "")
            version_range = acceptable.get("versionRange", "*")
            for record in self._records:
                if record.profile_id != acceptable_id:
                    continue
                if _is_version_compatible(record.version, version_range):
                    all_acceptable.append(record)

        if not all_acceptable:
            return None
        return max(all_acceptable, key=lambda e: _parse_semver(e.version))

    def _find(self, profile_id: str, version: str) -> ProfileRecord | None:
        for entry in self._records:
            if entry.profile_id == profile_id and entry.version == version:
                return entry
        return None


def _split_requested_profile(requested_profile: str) -> tuple[str, str | None]:
    if "@" not in requested_profile:
        return requested_profile, None
    profile_id, version = requested_profile.rsplit("@", 1)
    return profile_id, version


def _parse_semver(version: str) -> tuple[int, int, int]:
    tokens = version.split(".")
    if len(tokens) != 3:
        raise ValueError(f"invalid semver: {version}")
    try:
        return (int(tokens[0]), int(tokens[1]), int(tokens[2]))
    except ValueError as exc:
        raise ValueError(f"invalid semver: {version}") from exc


def _is_version_compatible(version: str, version_range: str) -> bool:
    if version_range in {"", "*"}:
        return True

    if version_range.endswith(".x"):
        major = version_range.split(".", 1)[0]
        try:
            return _parse_semver(version)[0] == int(major)
        except ValueError:
            return False

    if version_range.startswith("^"):
        lower = version_range[1:]
        lower_v = _parse_semver(lower)
        current = _parse_semver(version)
        return current[0] == lower_v[0] and current >= lower_v

    return version == version_range
