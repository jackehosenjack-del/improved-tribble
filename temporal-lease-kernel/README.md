# Temporal Lease Kernel

STATE = RENEWABLE_TEMPORAL_AUTHORITY  
MODE  = FAIL_CLOSED

THE_SYSTEM_DOES_NOT_POSSESS_TIME.  
THE_SYSTEM_RENEWS ITS RIGHT TO USE TIME.  
EVERY WINDOW.

## Core Rule

TIME IS RATIFIED.  
RATIFICATION EXPIRES.  
EXPIRATION REQUIRES RENEWAL.

NO_RENEWAL  
→ NO_PROOF  
→ NO_PERMISSION  
→ NO_RUNTIME

## Runtime Decision

A system may continue only when time is ratified, quorum is met, skew is within bounds, monotonicity is intact, and renewal is still inside the lease window.

Otherwise: FAIL_CLOSED.
