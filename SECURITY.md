# Security guidelines

- Use only cameras you own or are explicitly authorized to access.
- Device credentials should be root-readable only under `/etc`, outside the repository.
- The tested dispatcher endpoint uses plaintext HTTP; relay server IP addresses are restricted to a user-edited allowlist. Do not trust arbitrary returned IPs.
- Both cloud relay and the camera's embedded protocol are experimental; treat the network and endpoints as untrusted.
- Never post camera IDs, passwords, IMEI, ICCID, QR codes, ticket/session tokens, or clips in public issues.
- Rotate credentials if compromised. Firmware/protocol upgrades can break compatibility.
