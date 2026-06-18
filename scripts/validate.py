from search_visibility_auditor.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["validate", *(__import__("sys").argv[1:])]))

