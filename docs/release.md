# Release packet

`works release` is the last read-only check before a person releases a proved fix. It does not
publish anything.

```bash
works release <task-id>
works release <task-id> --json
```

The packet binds:

- the latest finished run;
- the exact base commit;
- the proof SHA-256;
- the plan approval and whether it is bound to the same commit;
- the release approval, if one exists;
- blockers: task not proved, missing proof, verdict not allow, blocked independent review, missing
  gate, or an approval bound to another commit.

Exit code `0` means the packet is ready for a publisher; `8` means blocked. The packet explicitly
says `publisher: not configured` because branch/PR/issue adapters are M3 work. Producing a packet is
not a release.
