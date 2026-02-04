import os
import sys
import warnings

# [Windows Only] SSLKEYLOGFILE can trigger the "no OPENSSL_Applink" error.
# OpenSSL on Windows requires an 'Applink' interface to safely perform I/O
# (like logging keys) across different C-Runtimes (CRT). Since CPython doesn't
# provide this bridge and manages I/O independently, OpenSSL fails to access
# Windows stdio, leading to a crash or the "no OPENSSL_Applink" error.
if os.environ.get("SSLKEYLOGFILE") and sys.platform == "win32":
    warnings.warn(
        "Detected SSLKEYLOGFILE environment variable, which may cause "
        "'no OPENSSL_Applink' errors. If you encounter this issue, try "
        "unsetting or removing the variable temporarily.",
        UserWarning,
        2,
    )
