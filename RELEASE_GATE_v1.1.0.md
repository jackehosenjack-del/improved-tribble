# Universal QR Clone v1.1.0 — Release Gate

## State

```text
STATE: RELEASE_CANDIDATE
MODE: FAIL_CLOSED
VERSION: v1.1.0
```

## Required Checks

- [ ] Branch exists: `feature/universal-qr-clone-v1`
- [ ] v1.1.0 files committed
- [ ] `pytest` passes locally
- [ ] GitHub Actions CI green
- [ ] `CHANGELOG.md` includes `[1.1.0]`
- [ ] `config.json.example` exists
- [ ] No runtime artifacts committed
- [ ] No secrets committed
- [ ] Rollback command documented

## Functional Checks

- [ ] `python main.py clone --payload "https://example.com"`
- [ ] `python main.py scan --image input/my_qr.png`
- [ ] `python main.py history --limit 5`
- [ ] `python main.py batch --folder input/`
- [ ] `python main.py batch-clone --folder input/ --output-folder exports/batch`
- [ ] `python main.py --config config.json.example clone --payload "https://example.com"`

## Safety Checks

- [ ] Empty payload denied
- [ ] `javascript:` blocked
- [ ] `data:` blocked
- [ ] `file:` blocked
- [ ] `https://example.com` allowed low risk
- [ ] `http://example.com` allowed medium risk
- [ ] Punycode domain blocked
- [ ] URL with `@` blocked
- [ ] Shortener domain marked medium risk
- [ ] Duplicate payload returns warning

## Release Decision

```text
IF all_required_checks_pass
THEN RELEASE_ALLOWED
ELSE FAIL_CLOSED
```

## Rollback

```bash
git checkout main
git revert <merge_commit_sha>
git push origin main
```

## Final Approval

```text
STATE: RELEASE_ALLOWED
MODE: HUMAN_APPROVED
```
