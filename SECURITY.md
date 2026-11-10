# Security

Please report a vulnerability privately through GitHub private vulnerability reporting:
[Report a vulnerability](https://github.com/bajalabs/hs-crosswalk-us-mx/security/advisories/new).
Do not open a public issue for it.

The builder downloads public files and checks each one against the sha256 pinned in
`manifests/sources.json` before using it. It needs no credentials and the CI uses no
secrets. Reports about the integrity of a source file, of a release asset or of the
download and extraction code are in scope.

We aim to acknowledge a report within five working days.
