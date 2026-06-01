# Release and Packaging Notes

This file records project-local rules for future release work.

## Do Not Package Casually

- Do not run `packaging\build_release.bat` unless the user explicitly asks for a package or release build.
- Normal code changes, tests, docs edits, and branch checkpoints should not rebuild `dist`.
- Packaging is slow and rewrites large ignored outputs under `dist`, so treat it as a release step.

## Version First

Before any intentional package or GitHub Release replacement, update the version first.

Current version locations:

- `packaging/installer/czn_auto.iss`: `#define MyAppVersion "..."`
- `README.md`: installer filename examples such as `CZNAutoSetup-x.y.z.exe`
- GitHub Release tag/name if publishing, for example `v0.1.1`

Recommended flow:

1. Finish and test source changes.
2. Decide the next version number.
3. Update all visible version references.
4. Run lightweight checks.
5. Run `packaging\build_release.bat` only after the version update is committed or ready to commit.
6. If replacing GitHub Release assets, make sure the tag points at the intended commit.

## Quick Checks Before Packaging

Run these before a package build:

```powershell
python -m py_compile src\main.py src\state_check.py src\diagnose_input.py src\commands\cli.py src\commands\state_check.py src\commands\diagnose_input.py src\core\settings.py src\core\models.py src\vision\detector.py src\system\io_system.py src\system\controls.py src\actions\common.py src\ui\logging.py src\state_machines\live\session.py
python -m json.tool config.example.json > $null
```

For input-backend changes, also run a short bounded live test instead of immediately doing a full package build.
