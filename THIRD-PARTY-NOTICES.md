<!--
SPDX-License-Identifier: LicenseRef-Shinkawa-NC-1.1
Copyright (c) 2025 Shinkawa
-->

# Third-Party / External Notices

This project executes an external shell script specified via `SCRIPT_SOURCE_URL`.
That script is **not** distributed with this repository.

- Name: checkRisk.sh
- Repository: https://github.com/shinkawamisaki/checkRisk
- License: Shinkawa Non-Commercial License v1.1 (see that repository). Review before use.

Runtime dependencies bundled by this repository: none (the Lambda uses only the Python standard library
and the boto3 that AWS Lambda provides). Build-time dependencies are listed in `package.json`.
