# LAN and tablet access

Spec written before code. This is the increment that lets a person in a cure room use the record from a
tablet, without putting the record on the internet and without pretending a shared office login is
authentication.

## Why loopback was right, and why it is not enough

`serve()` refused anything but loopback for a reason: any page in the operator's browser can post to
`127.0.0.1`, so the boundary is the session token plus the `Origin` check. On a LAN that reasoning
weakens, because a request arrives from another machine and the server can no longer assume the person
holding the browser is the person at the keyboard.

The facility's real problem is physical: the person who harvests is standing in a wet room with gloves
on, and the record is on a PC in an office. Walking to the office to type a weight is how a record falls
a day behind. That is the pain this increment answers.

## The trust model, stated plainly

- **A LAN is a boundary the facility owns.** The appliance does not reach the internet, and this
  increment does not open a port to it. If the facility wants a tablet in the cure room, that tablet is
  on a network the facility controls; a segmented VLAN with no route out is the recommendation, written
  in the guide.
- **Every device is paired explicitly, by a person, at the server.** A device holds a token; a token is
  a credential; nothing that reaches a tablet is guessable, and nothing is printed on a sticker.
- **A paired device is not a person.** The operator name stays a claim, exactly as it is on loopback.
  Per-person passphrases are a separate increment with its own spec (`docs/flows/operators.md`), and the
  LAN build says so on the pair page rather than implying otherwise.
- **HTTP on a LAN by default, TLS when the facility has a certificate.** Standard library can load a
  cert (`ssl.SSLContext.load_cert_chain`) and cannot generate one; inventing a cert generator with no
  crypto dependency would be worse than saying "provide a PEM". `--tls-cert`/`--tls-key` are accepted,
  and without them the bind line says, in words, that traffic on this network is unencrypted.

## What changes

1. **`coontie serve --lan`** binds the machine's LAN address instead of loopback. Loopback stays the
   default, and `--lan` without a paired device is refused: a LAN build with nothing to authenticate
   would be a record on an open port.
2. **A pairing code, minted at the server.** `coontie terminal add --name "cure room tablet"` prints a
   ten-character code once and stores only a PBKDF2-HMAC-SHA256 verifier of it. The code is valid for
   **fifteen minutes** and for **one pairing**.
3. **`/pair`**: the tablet opens it, types the code, and receives a device cookie. The cookie's value is
   random, stored only as a verifier, and named in the devices table so an operator can see what is
   paired and revoke it.
4. **Paired devices only.** In LAN mode any request without a valid device cookie is sent to `/pair`,
   except `/health` (so a monitor can see the appliance is up, and it returns nothing else).
5. **Revocation** is a command: `coontie terminal revoke --id dv-…`. The next request from that tablet is
   sent to `/pair`.
6. **Rate limiting.** Five wrong codes from one address in fifteen minutes locks pairing from that
   address, with a sentence saying how long. An eight-to-ten character code is only unguessable if
   guessing is expensive.
7. **The ledger records pairing and revocation**, never the code and never the token: `device_paired`,
   `device_revoked`, each naming the device and the person who did it.

## Refusals

- `--lan` with no paired device
- `--lan` with an address that is not on this machine
- pairing with an expired, already-used or unknown code
- pairing attempts beyond the limit, from an address under lockout
- a device cookie whose device has been revoked
- `--tls-cert` without `--tls-key`, or a certificate that does not load

## A named public address, for a tunnel

A tunnel forwards to loopback and rewrites `Host`, so the two checks refuse it. The answer is not to
trust the header: it is `--public-url <scheme://host>`, typed by the operator, which adds exactly that
host to the `Host` allowlist and exactly that origin to the `Origin` allowlist.

- `normalise_public_url` accepts `https://host` and `https://host/`, refuses a missing scheme, a scheme
  that is not http(s), and any path, query or fragment. A path would mean the operator is pointing the
  flag at something the `Host` check does not cover.
- The bind line prints the address and says, in words, that it is public: anyone holding the link can
  read, writes still need the session token, and a passphrase should be enrolled first.
- Without the flag the tunnel hostname is still refused, which is a test. With it, every other hostname
  and origin is still refused, which is four more.

## What it does not do

- **No internet exposure.** No port forwarding, no tunnel, no cloud relay. A facility that wants remote
  access is asking for a different product decision, and this increment does not quietly grant it.
- **No per-person identity.** Named as the next increment, not pretended here.
- **No device code on the ledger.** The record is printed, exported and backed up; a credential in it
  would leak through every one of those paths.

## The gate

`tests/test_lan_gate.py`, over real HTTP against a server bound to a real LAN address where the machine
has one:

- loopback mode still needs no device, and still refuses a bad `Origin`
- LAN mode sends an unpaired request to `/pair` and serves `/health` regardless
- a wrong code five times locks that address, and the sixth says so
- a correct code pairs once; the same code a second time is refused
- the device cookie's value does not appear in the database, and a revoked device is refused on its next
  request
- a POST from a paired device with a foreign `Origin` is refused
- the ledger holds `device_paired` and `device_revoked` and neither a code nor a token
