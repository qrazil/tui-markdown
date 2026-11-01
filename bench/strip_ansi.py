import re,sys
d=sys.stdin.buffer.read().decode()
d=re.sub(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)","",d)
d=re.sub(r"\x1b\[[0-9;:?]*[A-Za-z]","",d)
print("\n".join(l.rstrip() for l in d.split("\n")))
