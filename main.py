"""Campus Guide Robot — unified entry point.

Usage::

    python main.py                  # full navigation workflow
    python main.py --demo           # voice-controlled motion demo
    python main.py --config path/to/config.yaml
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure src/ is on the Python path so internal imports work regardless
# of where the script is invoked from.
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

logger = logging.getLogger("robot")


def run_navigation(config_path: str):
    """Launch the full campus-guide state-machine."""
    from robot import Robot

    robot = Robot(config_path)
    robot.run()


def run_demo(config_path: str):
    """Launch the voice-controlled motion demo."""
    from demo import run as demo_run

    demo_run(config_path)


# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="BJEA Campus Guide Robot")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the voice-controlled motion demo instead of full navigation.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration YAML (default: config.yaml).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.demo:
        run_demo(args.config)
    else:
        run_navigation(args.config)


if __name__ == "__main__":
    main()
