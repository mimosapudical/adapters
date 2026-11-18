import argparse
from pathlib import Path
from .adapter import MedCalcBenchVerifiedAdapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument("--cache-dir", type=Path, default=Path.home()/".cache"/"harbor-medcalc")
    parser.add_argument("--split", choices=["test"], default="test")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    paths = MedCalcBenchVerifiedAdapter(**vars(args)).run()
    print(f"Generated {len(paths)} tasks")


if __name__ == "__main__":
    main()
