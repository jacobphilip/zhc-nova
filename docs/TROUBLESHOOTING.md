# Troubleshooting

## DB Initialization Fails

- Symptom: `unable to open database file`
- Check: parent directory exists and is writable
- Fix: run `mkdir -p storage/tasks` then `./scripts/db_init.sh`

## Router Cannot Dispatch Heavy Task

- Symptom: dispatch event shows SSH failure
- Check: `ZHC_UBUNTU_HOST`, SSH key auth, remote repo path
- Fix: test manually with `ssh <host> 'hostname'`

## zrun Stub Not Executing Real OpenCode

- Symptom: output says stub run
- Check: `ZHC_ENABLE_REAL_OPENCODE=1` and `opencode` in PATH
- Fix: authenticate OpenCode, then rerun

## Task Stuck in Running

- Symptom: no final state after failure
- Fix: append failure event and set status manually:

```bash
python3 shared/task-registry/task_registry.py update --task-id <task_id> --status failed --detail "manual recovery"
```

## systemd Unit Not Starting

- Check unit paths and executable permissions
- Run:

```bash
systemctl --user daemon-reload
systemctl --user status zhc-task-router.service
journalctl --user-unit zhc-task-router.service -n 100
```
