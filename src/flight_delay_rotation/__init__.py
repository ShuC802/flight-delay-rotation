"""Package scaffold created by `uv init`.

The pipeline runs as standalone scripts under scripts/, not as an imported
library. This package exists so the project is installable and so
`uv sync --locked` has something to build.
"""


def main() -> None:
    print("This project runs as scripts; see the Run section of README.md.")
