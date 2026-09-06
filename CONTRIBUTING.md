# Contributing (developers)

Product users install `Uryx-Setup.exe` — they do not clone a repo.
This file is for people changing the code.

The **public product** repository is [`uguredm/Uryx`](https://github.com/uguredm/Uryx).
Private R&D stays on `uguredm/uryx-test`.

## Requirements

- Windows 11
- Node.js 20+
- Docker Desktop with WSL2
- Do **not** commit `.env`

## Local run

```powershell
git clone https://github.com/uguredm/Uryx.git
cd Uryx
copy .env.example .env
.\scripts\start-dev.ps1
```

`@uryx/shared-types` stays at **0.1.0** (contract package, independent of the app semver).

## Tests

```powershell
cd apps\api
python -m pytest
cd ..\desktop
npm test
npm run typecheck
```

Architecture: `ARCHITECTURE.md`. Do not `docker compose down -v`.
