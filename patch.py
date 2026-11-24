import argparse, os, re, shutil, struct, subprocess, sys, tempfile, zipfile
import UnityPy
from UnityPy.streams import EndianBinaryReader

A = "assets/bin/Data/data.unity3d"
B = "lib/arm64-v8a/libil2cpp.so"
off = 0x1812658
chk = bytes.fromhex("ff4301d1f85f01a9")
fix = struct.pack("<II", 0x52800020, 0xD65F03C0)
g = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def sh(*c, cwd=None):
    r = subprocess.run(c, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(c[0] + " failed\n" + (r.stderr or r.stdout))


def ids(d, new1, new2):
    e = UnityPy.load(d)
    old = None
    for f in e.file.files.values():
        if old or not hasattr(f, "objects"):
            continue
        for o in f.objects.values():
            if o.type.name == "MonoBehaviour":
                m = g.findall(o.get_raw_data())
                if len(m) == 2:
                    old = m
                    break
    if not old:
        sys.exit("no ids found")
    print(old[0].decode(), old[1].decode())
    t = {old[0]: new1.encode(), old[1]: new2.encode()}
    c = 0
    for n, f in list(e.file.files.items()):
        if not hasattr(f, "objects"):
            continue
        x = bytes(f.reader.bytes)
        h = sum(x.count(k) for k in t)
        for k, v in t.items():
            x = x.replace(k, v)
        r = EndianBinaryReader(x)
        r.flags, r.name, r.path = f.flags, n, getattr(f, "path", n)
        e.file.files[n] = r
        c += h
        if h:
            print(n, h)
    if c != 4:
        sys.exit("expected 4, got %d" % c)
    return e.file.save(packer="none")


def lib(d):
    if d[off:off + 8] != chk:
        sys.exit("wrong libil2cpp, not the jan 30 build")
    d = bytearray(d)
    d[off:off + 8] = fix
    return bytes(d)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("apk", nargs="?", default="lethalape.apk")
    p.add_argument("--pun", required=True)
    p.add_argument("--voice", required=True)
    p.add_argument("-o", "--out")
    p.add_argument("--keystore", default=os.path.expanduser("~/.android/debug.keystore"))
    a = p.parse_args()

    for t in ("zip", "zipalign", "apksigner"):
        if not shutil.which(t):
            sys.exit(t + " not found")
    for i in (a.pun, a.voice):
        if not g.fullmatch(i.encode()):
            sys.exit("bad id: " + i)
    if not os.path.exists(a.apk):
        sys.exit(a.apk + " not found, name your apk lethalape.apk")
    if not os.path.exists(a.keystore):
        sys.exit("no keystore at " + a.keystore)

    out = a.out or re.sub(r"\.apk$", "", a.apk) + "_patched.apk"
    w = tempfile.mkdtemp()
    z = zipfile.ZipFile(a.apk)
    for path, data in ((A, ids(z.read(A), a.pun, a.voice)), (B, lib(z.read(B)))):
        dst = os.path.join(w, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(data)

    t1, t2 = os.path.join(w, "1.apk"), os.path.join(w, "2.apk")
    shutil.copy(a.apk, t1)
    sh("zip", "-X", "-0", t1, A, cwd=w)
    sh("zip", "-X", "-6", t1, B, cwd=w)
    sh("zipalign", "-f", "4", t1, t2)
    sh("apksigner", "sign", "--ks", a.keystore, "--ks-pass", "pass:android",
       "--key-pass", "pass:android", "--out", out, t2)
    shutil.rmtree(w)
    print(out)


main()
