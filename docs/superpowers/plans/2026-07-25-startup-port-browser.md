# Startup Port Cleanup and Browser Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both platform launchers terminate all listeners on the configured port and open the application URL after a short delay.

**Architecture:** Keep Waitress as the foreground process. Use existing operating-system commands for port cleanup and detached native commands for delayed browser launch; add no dependencies or launcher module.

**Tech Stack:** Bash, Windows batch, PowerShell, Python `unittest`

## Global Constraints

- Modify only `start_linux.sh`, `start_windows.bat`, and one focused test file.
- Terminate every process listening on `CAMPUS_PORT`, defaulting to `5000`.
- Browser-launch failure must not prevent Waitress from running.
- Preserve terminal logs and Ctrl+C by keeping Waitress in the foreground.

---

### Task 1: Cross-platform startup behavior

**Files:**
- Create: `tests/test_start_scripts.py`
- Modify: `start_linux.sh`
- Modify: `start_windows.bat`

**Interfaces:**
- Consumes: `CAMPUS_HOST` and `CAMPUS_PORT` environment variables.
- Produces: launchers that free the selected TCP port, schedule the URL to open, and execute Waitress in the foreground.

- [ ] **Step 1: Write the failing tests**

Create a `unittest.TestCase` that reads both scripts. Assert Linux contains `fuser -k`, a background block with `sleep 1`, `xdg-open`, and `exec .venv/bin/python -m waitress`. Assert Windows contains `Get-NetTCPConnection`, `Stop-Process -Id $_ -Force`, `Start-Sleep -Seconds 1`, `Start-Process`, and a foreground Waitress command.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest -v tests.test_start_scripts`

Expected: FAIL because neither launcher contains port cleanup or browser-launch commands.

- [ ] **Step 3: Implement the Linux launcher**

After resolving `host` and `port`, require `fuser`; if the port is occupied, run `fuser -k "${port}/tcp"` and exit with a concise error if it fails. Start a background subshell that sleeps one second and calls `xdg-open`, while treating a missing or failed opener as non-fatal. Keep the existing final `exec` command.

- [ ] **Step 4: Implement the Windows launcher**

Before Waitress, invoke PowerShell with `Get-NetTCPConnection -State Listen -LocalPort %CAMPUS_PORT%`, select unique owner PIDs, and pass each to `Stop-Process -Force`; stop on failure. Use `start "" /B powershell` to sleep one second and invoke `Start-Process` for the URL. Keep the existing Waitress command unwrapped so it remains attached to the console.

- [ ] **Step 5: Run focused and regression tests**

Run: `.venv/bin/python -m unittest -v tests.test_start_scripts`

Expected: PASS.

Run: `.venv/bin/python -m unittest -v`

Expected: all tests PASS.

Run: `bash -n start_linux.sh && git diff --check`

Expected: both commands exit successfully without output.

- [ ] **Step 6: Commit**

```bash
git add tests/test_start_scripts.py start_linux.sh start_windows.bat
git commit -m "feat: automate startup port cleanup"
```
