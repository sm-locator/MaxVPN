# Brume 3 VLESS subscription deployment

Date: 2026-11-17
Hardware: GL-MT5000, CN firmware
Feature source: PR #4
Baseline commit: 30cae46

The live router uses a minimal merge over its existing
appliance files, not a full replacement from PR #4.

Validated on router:
- VLESS API HTTP 200
- Invalid subscription preview HTTP 422
- Existing 14 profiles unchanged
- sing-box running; runtime mode WAN

Deployed file SHA-256:

server.py: 3b3919434698d31244cec87247d10eafacf31eba1f0a8fa3fe539d0cf07c53f5
vless_control.py: ae97cedaa795f06af99e898b92bf80cb06f1c40558213b353df949d5ec772189
vless_subscription.py: 03d1f623034bc02861f593866fb827d41146c5e343f7f65e5a4070fb4ceb5c64
index.html: c50d460900af781e5c32f740eab2484da1defe10eaf95ab341231ef906bc3649

The deployment-specific source diff is retained
privately, outside this repository.

Do not replace live routing, DNS or WAN fallback code
from PR #4 without a separate compatibility review.
