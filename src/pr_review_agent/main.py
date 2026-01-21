"""CLI entrypoint for PR Review Agent."""

import argparse
import sys


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI-powered PR review agent",
        prog="pr-review-agent",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument("--config", default=".ai-review.yaml", help="Config file path")
    parser.add_argument("--post-comment", action="store_true", help="Post comment to GitHub")

    args = parser.parse_args()
    print(f"Reviewing PR #{args.pr} in {args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
