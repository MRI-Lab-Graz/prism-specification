# Released survey IDs

`survey-ids.txt` lists every released PRISM survey ID (identifiers only, one per line); it is the source of truth.
It is frozen: lines are never removed or changed (CI checks this against the base commit). New IDs are added by pull
request.

## Deprecating an ID

An ID that should no longer be used keeps its line and gets an entry in `survey-deprecated.json` (the file appears with
the first deprecation), naming the ID to use instead:

```json
{"prism:tipi.tipi01": {"ReplacedBy": "prism:tipi.tipi02"}}
```

Both IDs must be released, and the replacement must not be deprecated itself (point every older entry at the newest ID).
A deprecated item or score may then leave its template. `python scripts/check_mappings.py` checks the file and warns
about links on a deprecated ID.
