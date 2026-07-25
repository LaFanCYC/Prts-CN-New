# Startup Port Cleanup and Browser Launch

## Scope

Update `start_linux.sh` and `start_windows.bat` only. Before Waitress starts, each script terminates every process listening on `CAMPUS_PORT` (default `5000`). It then schedules the application URL to open after a short fixed delay and runs Waitress in the foreground.

## Platform Behavior

- Linux uses `fuser` to terminate listeners on `${port}/tcp`. If `fuser` is unavailable, the script exits with a clear installation message. `xdg-open` opens the URL when available; missing browser integration prints the URL without blocking startup.
- Windows invokes PowerShell to find `Get-NetTCPConnection` owners and stop them with `Stop-Process -Force`. A detached PowerShell command waits briefly and opens the URL with `Start-Process`.

No attempt is made to identify whether a listener belongs to this project: the requested behavior is to terminate all processes occupying the selected port.

## Errors and Process Lifecycle

Failure to release the port stops startup with a concise error. Browser-launch failures do not stop the server. Waitress remains the foreground process so terminal logs and Ctrl+C continue to work as before.

## Verification

A small shell-oriented test inspects both launchers for the required port cleanup, delayed browser launch, and foreground Waitress invocation. Existing Python tests remain unchanged and are run as a regression check.
