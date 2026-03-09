from __future__ import annotations

import importlib
import warnings



def test_legacy_mcp_adapter_emits_deprecation_warning() -> None:
    import shared.nexus_common.mcp_adapter as legacy

    legacy = importlib.reload(legacy)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", DeprecationWarning)
        legacy.resolve_jwt_token()

    assert any(issubclass(item.category, DeprecationWarning) for item in captured)
