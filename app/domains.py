"""Turn pasted text into a clean list of company domains."""
import re

MAX_DOMAINS = 15
_DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
# The server fetches these hosts later, so names that can only be private are refused here.
_PRIVATE_SUFFIXES = (".local", ".internal", ".localhost", ".test", ".example", ".invalid", ".lan")


def parse_domains(text):
    valid, rejected = [], []

    def reject(raw, reason):
        rejected.append({"input": raw[:80], "reason": reason})

    for raw in re.split(r"[\s,;]+", text.strip()):
        if not raw:
            continue
        if "@" in raw:
            reject(raw, "This is an email address, not a domain.")
            continue
        d = re.sub(r"^[a-z][a-z0-9+.-]*://", "", raw.lower())
        d = re.split(r"[/?#:]", d, 1)[0].rstrip(".")
        if d.startswith("www."):
            d = d[4:]
        if not _DOMAIN.match(d) or d.endswith(_PRIVATE_SUFFIXES):
            reject(raw, "Not a public domain name.")
        elif d in valid:
            reject(raw, "Duplicate of a domain already in the list.")
        elif len(valid) >= MAX_DOMAINS:
            reject(raw, "Over the %d-domain cap for one run." % MAX_DOMAINS)
        else:
            valid.append(d)
    return {"valid": valid, "rejected": rejected, "cap": MAX_DOMAINS}
