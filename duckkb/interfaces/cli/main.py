from __future__ import annotations

import argparse
import json
from typing import Any

from duckkb.interfaces.mcp import tools


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="duckkb")
    parser.add_argument("--kb-path", dest="kb_path", default=None)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("sync")
    sub.add_parser("schema")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    sql = sub.add_parser("sql")
    sql.add_argument("statement")

    imp = sub.add_parser("import")
    imp.add_argument("table")
    imp.add_argument("jsonl")

    args = parser.parse_args(argv)

    if args.command == "sync":
        result = tools.sync_knowledge_base(args.kb_path)
        return _print(result)
    if args.command == "schema":
        result = tools.get_schema_info(args.kb_path)
        return _print(result)
    if args.command == "search":
        result = tools.smart_search(args.kb_path, args.query, limit=args.limit)
        return _print(result)
    if args.command == "sql":
        result = tools.query_raw_sql(args.kb_path, args.statement)
        return _print(result)
    if args.command == "import":
        lines = args.jsonl.split("\\n")
        result = tools.validate_and_import(args.kb_path, args.table, lines)
        return _print(result)
    parser.print_help()
    return 1


def _print(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
