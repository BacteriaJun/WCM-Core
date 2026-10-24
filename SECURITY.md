# Integrity and provisioning

Mission-64 CRC detects incidental task-data corruption. The SHA-256 manifest
checks distributed file contents. Both are unsigned; publisher and task-author
authentication require a separate mechanism.

The control model assumes authorized offline provisioning, immutable task
configuration during execution, qualified sensor and energy inputs, and
settlement feedback associated with the active transaction. Target integration
includes physical output protection and frontend qualification.

Report potential vulnerabilities privately to the maintainer through repository
private vulnerability reporting when available.
