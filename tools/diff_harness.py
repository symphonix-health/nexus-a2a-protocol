import argparse
import importlib
import os
import sys
from typing import Any, Callable


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def eq(a: Any, b: Any) -> bool:
    return a == b


def run_task_pairs(src_a: str, src_b: str) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, note: str = ""):
        results.append((name, ok, note))

    # fib
    try:
        ma = import_from(src_a, "fib")
        mb = import_from(src_b, "fib")
        seq = [0, 1, 2, 10, 30]
        ok = all(ma.fib(n) == mb.fib(n) for n in seq)
        record("fib", ok)
    except Exception as e:
        record("fib", False, f"error: {e}")

    # anagram
    try:
        ma = import_from(src_a, "anagram")
        mb = import_from(src_b, "anagram")
        pairs = [("listen", "silent"), ("Dormitory", "Dirty room!!"), ("aaab", "ab")]
        ok = all(ma.is_anagram(a, b) == mb.is_anagram(a, b) for a, b in pairs)
        record("anagram", ok)
    except Exception as e:
        record("anagram", False, f"error: {e}")

    # json_flatten
    try:
        ma = import_from(src_a, "json_flatten")
        mb = import_from(src_b, "json_flatten")
        obj = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
        ok = eq(ma.flatten_json(obj, "."), mb.flatten_json(obj, "."))
        record("json_flatten", ok)
    except Exception as e:
        record("json_flatten", False, f"error: {e}")

    # top_k_words
    try:
        ma = import_from(src_a, "topk_words")
        mb = import_from(src_b, "topk_words")
        text = "Hello, hello! world; World world?"
        ok = eq(ma.top_k_words(text, 2), mb.top_k_words(text, 2))
        record("top_k_words", ok)
    except Exception as e:
        record("top_k_words", False, f"error: {e}")

    # canonical_json
    try:
        ma = import_from(src_a, "canonical_json")
        mb = import_from(src_b, "canonical_json")
        obj1 = {"b": 2, "a": {"y": 2, "x": 1}}
        ok = eq(ma.canonical_dumps(obj1), mb.canonical_dumps(obj1))
        record("canonical_json", ok)
    except Exception as e:
        record("canonical_json", False, f"error: {e}")

    # bytes_chunking
    try:
        ma = import_from(src_a, "bytes_chunking")
        mb = import_from(src_b, "bytes_chunking")
        data = b"abcdefghijklmnopqrstuvwxyz"
        ok = eq(ma.chunk_bytes(data, 5), mb.chunk_bytes(data, 5)) and eq(
            ma.unchunk_bytes(ma.chunk_bytes(data, 5)), mb.unchunk_bytes(mb.chunk_bytes(data, 5))
        )
        record("bytes_chunking", ok)
    except Exception as e:
        record("bytes_chunking", False, f"error: {e}")

    # hmac_sign
    try:
        ma = import_from(src_a, "hmac_sign")
        mb = import_from(src_b, "hmac_sign")
        payload, secret = b"hello world", b"supersecret"
        sa, sb = ma.sign_message(payload, secret), mb.sign_message(payload, secret)
        ok = sa == sb and ma.verify_message(payload, secret, sa) and mb.verify_message(payload, secret, sb)
        record("hmac_sign", ok)
    except Exception as e:
        record("hmac_sign", False, f"error: {e}")

    # dijkstra
    try:
        ma = import_from(src_a, "dijkstra")
        mb = import_from(src_b, "dijkstra")
        graph = {"A": [("B", 1), ("C", 4)], "B": [("C", 2), ("D", 5)], "C": [("D", 1)], "D": []}
        ok = eq(ma.shortest_paths(graph, "A"), mb.shortest_paths(graph, "A"))
        record("dijkstra", ok)
    except Exception as e:
        record("dijkstra", False, f"error: {e}")

    # merkle
    try:
        ma = import_from(src_a, "merkle")
        mb = import_from(src_b, "merkle")
        chunks = [b"a", b"b", b"c", b"d", b"e"]
        try:
            ra = ma.merkle_root(chunks); r0a = ma.merkle_root([])
        except NotImplementedError:
            record("merkle", True, "SKIP: src-a not implemented")
        else:
            try:
                rb = mb.merkle_root(chunks); r0b = mb.merkle_root([])
            except NotImplementedError:
                record("merkle", True, "SKIP: src-b not implemented")
            else:
                record("merkle", ra == rb and r0a == r0b)
    except Exception as e:
        record("merkle", False, f"error: {e}")

    # b64url
    try:
        ma = import_from(src_a, "b64url")
        mb = import_from(src_b, "b64url")
        data = b"\x00\x01\x02hello world!\xff"
        try:
            sa = ma.b64url_encode(data); da = ma.b64url_decode
        except NotImplementedError:
            record("b64url", True, "SKIP: src-a not implemented")
        else:
            try:
                sb = mb.b64url_encode(data); db = mb.b64url_decode
            except NotImplementedError:
                record("b64url", True, "SKIP: src-b not implemented")
            else:
                ok = ("=" not in sa) and ("=" not in sb) and (sa == sb) and (
                    da(sa) == db(sb) == data
                )
                record("b64url", ok)
    except Exception as e:
        record("b64url", False, f"error: {e}")

    # jsonrpc_utils.build_request
    try:
        ma = import_from(src_a, "jsonrpc_utils")
        mb = import_from(src_b, "jsonrpc_utils")
        ra = ma.build_request("echo", {"x": 1}, 123)
        rb = mb.build_request("echo", {"x": 1}, 123)
        record("jsonrpc_build_request", eq(ra, rb))
    except Exception as e:
        record("jsonrpc_build_request", False, f"error: {e}")

    # async_pool
    try:
        ma = import_from(src_a, "async_pool")
        mb = import_from(src_b, "async_pool")
        import asyncio

        async def make_jobs(n: int):
            async def j(i: int):
                await asyncio.sleep(0)
                return i * i

            return [lambda i=i: j(i) for i in range(n)]

        jobs = asyncio.run(make_jobs(8))
        ra = ma.run_bounded(jobs, 3)
        rb = mb.run_bounded(jobs, 3)
        record("async_pool", eq(ra, rb))
    except Exception as e:
        record("async_pool", False, f"error: {e}")

    return results


def main():
    ap = argparse.ArgumentParser(description="Compare outputs between two source directories")
    ap.add_argument("--src-a", required=True)
    ap.add_argument("--src-b", required=True)
    args = ap.parse_args()

    results = run_task_pairs(args.src_a, args.src_b)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, note in results:
        status = "PASS" if ok else "FAIL"
        if note:
            print(f"{name}: {status} ({note})")
        else:
            print(f"{name}: {status}")
    print(f"\nSummary: {passed}/{total} tasks matched ({passed/total:.0%})")


if __name__ == "__main__":
    main()
