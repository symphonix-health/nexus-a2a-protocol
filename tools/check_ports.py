import json
from pathlib import Path


def main() -> int:
    cfg = json.loads(Path('config/agents.json').read_text())
    ports: dict[int, str] = {}
    conflicts: list[tuple[int, str, str]] = []

    for group, agents in cfg.get('agents', {}).items():
        for name, meta in agents.items():
            p = int(meta['port'])
            key = f"{group}/{name}"
            if p in ports:
                conflicts.append((p, ports[p], key))
            else:
                ports[p] = key

    for name, meta in cfg.get('backend', {}).items():
        p = int(meta['port'])
        key = f"backend/{name}"
        if p in ports:
            conflicts.append((p, ports[p], key))
        else:
            ports[p] = key

    print(f"TOTAL PORTS: {len(ports)}")
    if conflicts:
        print(f"CONFLICTS: {len(conflicts)}")
        for c in conflicts:
            print("CONFLICT", c)
        return 1
    else:
        print("CONFLICTS: 0")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
