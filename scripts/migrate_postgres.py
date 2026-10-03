#!/usr/bin/env python3
"""Run with the application stopped for a consistent migration or rollback."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import migration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('./storage'))
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--dry-run', action='store_true')
    action.add_argument('--export-files', action='store_true')
    parser.add_argument('--configure-local', action='store_true')
    args = parser.parse_args()
    if args.configure_local and (args.dry_run or args.export_files):
        parser.error('--configure-local requires an actual import')
    migration.configure_from_file(args.data)
    result = migration.export_files(args.data) if args.export_files else migration.import_files(args.data, args.dry_run)
    if args.configure_local:
        migration.save_configuration(args.data)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
