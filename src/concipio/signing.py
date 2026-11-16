"""Signatures: a person's statement that they read a doc or section as it
stands, written as fields under its title or heading, and provable with an
SSH signature over exactly the text it covers [CPO§W17, CPO§W53]."""

import base64
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from . import docs, doc_model

SIGNED, SIG = "Signed", "Sig"
NAMESPACE = "concipio"
ARMOR = ("-----BEGIN SSH SIGNATURE-----", "-----END SSH SIGNATURE-----")


@dataclass
class Target:
    """What a signature covers: a whole doc, by its title's section, or one
    section."""
    path: str
    kind: str
    section: doc_model.Node
    start: int
    end: int
    # Which of the doc's sections with this title and level it is, so two
    # sections headed alike are told apart.
    nth: int = 0

    @property
    def title(self):
        return self.section.title


# Implements [CPO§W17]
def targets(path, doc, sections=False):
    """The things in a doc a person may sign: the doc itself, under its
    title, and with `sections` each section below the title. A doc with no
    title to sign under offers its top-level sections instead."""
    tops = [s for s in doc.root.children if s.kind == "section"]
    out = []
    if tops and tops[0].level == 1:
        out.append(Target(path, "doc", tops[0], 0, len(doc.text)))
    elif not sections:
        return numbered([Target(path, "section", s, s.start, s.end) for s in tops])
    if sections:
        for s in doc.walk({"section"}):
            if not (out and s is out[0].section):
                out.append(Target(path, "section", s, s.start, s.end))
    return numbered(out)


def numbered(found):
    """The targets, each knowing which of its doc's like-headed sections it
    is."""
    seen = {}
    for t in found:
        key = (t.kind, plain_title(t.title), t.section.level)
        t.nth = seen.get(key, 0)
        seen[key] = t.nth + 1
    return found


# Implements [CPO§W17]
def fields_of(doc, target):
    """The signature fields a target carries, and the attribute list they
    are in, or ({}, None)."""
    attrs = doc_model.own_attrs(doc, target.section)
    if attrs is None:
        return {}, None
    return {k: v for k, v in attrs.fields.items() if k in (SIGNED, SIG)}, attrs


# Implements [CPO§D10]
def covered(doc, target, own_signed=True):
    """The text a signature covers, as bytes: the target's range, less every
    `Sig`, and less the `Signed` of every section nested in it; then any
    attribute list left empty, and any line that leaves blank; with line
    endings as `\\n` and trailing whitespace removed. Without `own_signed`,
    the target's own `Signed` goes too, to compare its text across
    signings."""
    _, own = fields_of(doc, target)
    if not own_signed:
        own = None
    data = doc.text
    cuts = []
    for a in doc.walk({"attrs"}):
        if not (target.start <= a.start < target.end):
            continue
        drop = {SIG} | ({SIGNED} if a is not own else set())
        if not drop & set(a.fields):
            continue
        body = data[a.start:a.end].decode()
        for key in drop & set(a.fields):
            body = re.sub(r"\s*(?<![\w.#-])" + re.escape(key) +
                          r"\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s}]+)", "", body)
        if re.fullmatch(r"\{:?\s*\}", body):
            line_start = data.rfind(b"\n", 0, a.start) + 1
            line_end = data.find(b"\n", a.end)
            line_end = len(data) if line_end < 0 else line_end
            if not (data[line_start:a.start] + data[a.end:line_end]).strip():
                cuts.append((line_start, min(line_end + 1, len(data)), b""))
                continue
            cuts.append((a.start, a.end, b""))
            continue
        cuts.append((a.start, a.end, body.encode()))
    out, at = [], target.start
    for a, b, text in sorted(cuts):
        a, b = max(a, target.start), min(b, target.end)
        if a < at:
            continue
        out.append(data[at:a])
        out.append(text)
        at = b
    out.append(data[at:target.end])
    text = b"".join(out).replace(b"\r\n", b"\n")
    return b"\n".join(line.rstrip() for line in text.split(b"\n")).rstrip(b"\n") + b"\n"


def signer_name(root):
    """The name a signature carries: `[signing] name` in `.cpo`, else git's
    `user.name` [CPO§W52]."""
    name = docs.config(root).get("signing", {}).get("name")
    if name:
        return name
    return subprocess.run(["git", "config", "user.name"], cwd=root, capture_output=True,
                          text=True).stdout.strip() or None


# Implements [CPO§W53]
def signing_key(root):
    """The key git signs commits with, as a path `ssh-keygen` can use, or
    None. A literal `key::` value is written to a temporary file."""
    out = subprocess.run(["git", "config", "user.signingkey"], cwd=root, capture_output=True,
                         text=True).stdout.strip()
    if not out:
        return None
    if out.startswith("key::"):
        import atexit
        fd, path = tempfile.mkstemp(suffix=".pub")
        os.write(fd, (out[5:] + "\n").encode())
        os.close(fd)
        atexit.register(lambda: os.path.exists(path) and os.unlink(path))
        return path
    return os.path.expanduser(out)


def signers_file(root):
    """The versioned file mapping signers' names to their public keys
    [CPO§W54]."""
    return Path(root) / docs.config(root).get("signing", {}).get("signers", ".cpo-signers")


# Implements [CPO§W54]
def name_of(signed):
    """The name in a `Signed` value, which ends with the time."""
    return signed.rsplit(" ", 1)[0] if " " in signed else signed


def principal(name):
    """How a signers file writes a name, whose fields whitespace separates:
    `Josh Ventura` as `Josh_Ventura`."""
    return "_".join(name.split())


# Implements [CPO§W53]
def sign_bytes(data, key):
    """An SSH signature over data, as the one-line value of `Sig`. The key's
    passphrase, if any, is asked for on the terminal by `ssh-keygen`."""
    out = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", NAMESPACE], input=data,
                         capture_output=True)
    if out.returncode != 0:
        raise SigningError(out.stderr.decode(errors="replace").strip() or "ssh-keygen failed")
    lines = [l for l in out.stdout.decode().splitlines() if l and l not in ARMOR]
    return "ssh:" + "".join(lines)


# Implements [CPO§W54]
def verify_bytes(data, sig, name, signers):
    """Whether `Sig` is a valid signature of the data by the named signer,
    as the signers file maps names to keys."""
    if not sig.startswith("ssh:") or not Path(signers).exists():
        return False
    body = sig[4:]
    try:
        base64.b64decode(body, validate=True)
    except ValueError:
        return False
    armored = "\n".join([ARMOR[0]] + [body[i:i + 70] for i in range(0, len(body), 70)]
                        + [ARMOR[1]]) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sig", delete=False) as f:
        f.write(armored)
    try:
        out = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", principal(name),
                              "-n", NAMESPACE, "-s", f.name], input=data, capture_output=True)
        return out.returncode == 0
    finally:
        os.unlink(f.name)


class SigningError(Exception):
    pass


# Implements [CPO§W51]
def signed_at(root, path, signed):
    """The commit that wrote a `Signed` value into a doc, or None if it is
    not committed yet."""
    # The value may be quoted either way, so git searches by pattern; the
    # oldest commit touching it wrote it.
    value = re.sub(r"([.\[\]*^$\\+?(){}|])", r"\\\1", signed)
    pattern = f"{SIGNED}[[:space:]]*=[[:space:]]*[\"']{value}[\"']"
    out = subprocess.run(["git", "log", "--format=%H", "-G", pattern, "--", path],
                         cwd=root, capture_output=True, text=True).stdout.split()
    return out[-1] if out else None


# Implements [CPO§W51]
def text_at(root, sha, path):
    out = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=root, capture_output=True)
    return out.stdout if out.returncode == 0 else None


# Implements [CPO§W51]
def plain_title(title):
    """A heading's title without the attribute lists written on its line,
    which signing itself may change."""
    return " ".join(doc_model.ATTR_LIST.sub(b"", title.encode()).decode().split())


def match_target(doc, target, path):
    """The same target in another version of a doc: the doc, or the section
    with the same title, attribute lists aside, and level."""
    for t in targets(path, doc, sections=target.kind == "section"):
        if t.kind == target.kind and plain_title(t.title) == plain_title(target.title) and \
                t.section.level == target.section.level and t.nth == target.nth:
            return t
    return None


# Implements [CPO§W51]
UNCOMMITTED = object()


def before(root, path, doc, target, display=False):
    """The covered text as the signature now in the target last saw it, at
    the commit that wrote it. A signature not committed yet was written for
    the text as it stands, so it has nothing before it: UNCOMMITTED, or
    for `display`, the last commit's text, to show what changed since.
    None if the target was never signed, or did not exist then."""
    fields, _ = fields_of(doc, target)
    if SIGNED not in fields:
        return None
    sha = signed_at(root, path, fields[SIGNED])
    if sha is None and not display:
        return UNCOMMITTED
    old = text_at(root, sha or "HEAD", path)
    if old is None:
        return None
    then = doc_model.parse(old)
    t = match_target(then, target, path)
    return covered(then, t, own_signed=False) if t else None


# Implements [CPO§W54, CPO§W55]
def standing(root, path, doc, target, require=None):
    """Where a target's signature stands: unsigned; signed, as written or
    proven; stale, if its text changed since; invalid, if `Sig` does not
    verify though the text is unchanged; or unproven, if the project
    requires proof and there is none."""
    fields, _ = fields_of(doc, target)
    if SIGNED not in fields:
        return "unsigned"
    if SIG in fields and not signers_file(root).exists():
        # A Sig no signers file can check is neither proven nor forged.
        return "unverifiable"
    if SIG in fields and verify_bytes(covered(doc, target), fields[SIG],
                                      name_of(fields[SIGNED]), signers_file(root)):
        return "proven"
    if require and SIG not in fields:
        # Where proof is required, a signature without it is no signature,
        # whatever else changed.
        return "unproven"
    now = covered(doc, target, own_signed=False)
    then = before(root, path, doc, target)
    if then is UNCOMMITTED:
        # Written for the text as it stood when signed, and not committed
        # since, so a Sig that no longer verifies may mean an edit since as
        # well as a forgery; either way it needs signing again.
        return "stale" if SIG in fields else ("unproven" if require else "signed")
    if SIG in fields:
        # A section not found as it stood when signed, as after a rename,
        # has changed since; only unchanged text with a bad Sig is invalid.
        return "invalid" if then is not None and then == now else "stale"
    # A section not found as it stood when signed, as after a rename, has
    # changed since.
    if then is None or then != now:
        return "stale"
    return "unproven" if require else "signed"


# Implements [CPO§W52]
def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# Implements [CPO§W52]
def sign(root, path, target, name, key=None, when=None):
    """Sign a target in a doc's file: write `Signed`, then, with a key, the
    `Sig` of the text it covers, as splices, refusing if the file changed
    since it was read. Returns the value of `Signed`."""
    full = Path(root) / path
    original = full.read_bytes()
    doc = doc_model.parse(original)
    t = match_target(doc, target, path)
    if t is None:
        raise SigningError(f"{path} no longer has {target.title!r}; nothing was written")
    signed = f"{name} {when or stamp()}"
    step = doc_model.apply(original, [doc_model.set_field(doc, t.section, SIGNED, signed)])
    if key:
        doc2 = doc_model.parse(step)
        t2 = match_target(doc2, target, path)
        if t2 is None:
            raise SigningError(f"{path}: cannot find {target.title!r} again after writing "
                               "Signed; nothing was written")
        sig = sign_bytes(covered(doc2, t2), key)
        step = doc_model.apply(step, [doc_model.set_field(doc2, t2.section, SIG, sig)])
    current = full.read_bytes()
    if current != original:
        raise SigningError(f"{path} changed while it was being signed; nothing was written")
    full.write_bytes(step)
    return signed


# Implements [CPO§W19]
def directive(root, path, target, text):
    """Leave a directive instead of signing [CPO§W19]."""
    full = Path(root) / path
    original = full.read_bytes()
    doc = doc_model.parse(original)
    t = match_target(doc, target, path)
    if t is None:
        raise SigningError(f"{path} no longer has {target.title!r}; nothing was written")
    doc_model.write(full, doc, [doc_model.set_field(doc, t.section, "Restructure", text)])


# Implements [CPO§W20]
def signable_docs(root, defs):
    """The docs a person signs by default: the master, then every doc that
    defines tags, by path."""
    master = docs.config(root).get("master", "README.md")
    paths = {d.path for d in defs.values()} | ({master} if (Path(root) / master).exists() else set())
    return sorted(paths, key=lambda p: (p != master, p))


MESSAGES = {
    "stale": ("stale-signature", "{what} changed after {who} signed it; ask them to read "
              "the change and sign again with cpo sign"),
    "invalid": ("invalid-signature", "{what} has a Sig that does not verify as {who}'s, though "
                "its text is unchanged; a person must sign it again with cpo sign"),
    "unproven": ("unproven-signature", "{what} is signed by {who} with no Sig, and .cpo "
                 "requires proof; only {who} can sign it, with cpo sign"),
    "unverifiable": ("unverifiable-signature", "{what} has a Sig, but there is no signers file "
                     "to check it against; list each signer's public key in .cpo-signers"),
}


# Implements [CPO§W54, CPO§W55]
def lint_problems(root, files):
    """A problem for each signature that is stale, invalid, or unproven
    where the project requires proof."""
    from .lint import Problem
    require = docs.config(root).get("signing", {}).get("require")
    out = []
    for path in files:
        if not path.endswith(docs.DOC_EXTENSIONS):
            continue
        try:
            data = (Path(root) / path).read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            continue
        # A quick filter; attribute lists allow spaces around `=`.
        if not re.search(rb"(?<![\w.#-])" + SIGNED.encode() + rb"\s*=", data):
            continue
        doc = docs.model(data.decode(errors="replace"))
        for t in targets(path, doc, sections=True):
            fields, _ = fields_of(doc, t)
            if SIGNED not in fields:
                continue
            st = standing(root, path, doc, t, require)
            if st in MESSAGES:
                rule, msg = MESSAGES[st]
                what = "the doc" if t.kind == "doc" else f'section "{t.title}"'
                out.append(Problem(path, t.section.line, rule,
                                   msg.format(what=what, who=name_of(fields[SIGNED])),
                                   f"{t.kind}:{t.title}", 1))
    return out
