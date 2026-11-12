#!/usr/bin/env bash
# Install from a checkout, or download this script and run it with Bash.
set -euo pipefail

installer_ref="v0.3.1"
python_command=""
source_path=""
arguments=("$@")
argument_count=$#
for ((index=0; index<argument_count; index++)); do
  case "${arguments[index]}" in
    --python=*) python_command="${arguments[index]#--python=}" ;;
    --source=*) source_path="${arguments[index]#--source=}" ;;
    --python|--source)
      if ((index + 1 >= argument_count)); then
        printf 'Missing value after %s\n' "${arguments[index]}" >&2
        exit 2
      fi
      option="${arguments[index]}"
      index=$((index + 1))
      if [[ "$option" == "--python" ]]; then
        python_command="${arguments[index]}"
      else
        source_path="${arguments[index]}"
      fi
      ;;
  esac
done

if [[ -z "$python_command" ]]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
      python_command="$candidate"
      break
    fi
  done
fi
if [[ -z "$python_command" ]] || ! "$python_command" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
  printf 'Python 3.10+ is required. Install Python, or pass --python /absolute/path/to/python.\n' >&2
  exit 1
fi

helper=""
script_path="${BASH_SOURCE[0]:-}"
if [[ -n "$script_path" && -f "$script_path" ]]; then
  script_directory="$(cd "$(dirname "$script_path")" && pwd)"
  if [[ -f "$script_directory/install.py" ]]; then
    helper="$script_directory/install.py"
  fi
fi
if [[ -z "$helper" && -n "$source_path" && -f "$source_path/scripts/install.py" ]]; then
  helper="$source_path/scripts/install.py"
fi
if [[ -z "$helper" ]]; then
  temporary_directory="$(mktemp -d)"
  trap 'rm -rf "$temporary_directory"' EXIT
  helper="$temporary_directory/install.py"
  "$python_command" - "$helper" "https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/$installer_ref/scripts/install.py" <<'PY'
from pathlib import Path
import sys
from urllib.request import urlopen
with urlopen(sys.argv[2], timeout=30) as response:
    Path(sys.argv[1]).write_bytes(response.read())
PY
fi
"$python_command" "$helper" "$@"
