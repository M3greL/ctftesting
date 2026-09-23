# Common Ground personal blog

Common Ground is a small personal blog built with Python's standard library.
Alice, Bob, Diana, and Eve each have a short public post. Visitors can open a
post and follow its author to `/profile/stories?userid=<author-uuid>`. The UUID
is used only as the profile lookup identifier and is not displayed on author
profiles or when hovering over an author name.

## Run

```powershell
python server.py
```

The backup service is protected by a simple TCP port knock. In a second
terminal, run:

```powershell
python knock.py 127.0.0.1
```

The knocker connects to ports `8002`, `8003`, and `8004` in that order. The
backup service then accepts requests from that source address for 60 seconds.
The Common Ground website remains freely accessible on port `8001`. If the
backup is accessed before knocking, it returns an error; a wrong order or a
pause of more than five seconds resets the sequence. This is an
application-level teaching example, not a replacement for a host firewall.

Open <http://127.0.0.1:8001> at any time. The home page is public and contains one food post
by Alice and one gym post by Bob. Each post opens on its own page, and each
author name links to that author's profile. The **Authors** tab at `/authors`
lists a card for every author with published stories.

## Login

Visitors can log in with either seeded account:

| Username | Password |
| --- | --- |
| `alice` | `alicepass` |
| `bob` | `bobpass` |
| `diana` | `dianapass` |
| `eve` | `evepass` |

After logging in, open a private profile at `/users/user?userid=<user-uuid>`.
The route requires authentication, but intentionally uses the UUID from the
URL without checking that it belongs to the logged-in account. Changing
`userid` to another user's UUID therefore loads that user's private profile
and files, including downloadable files, demonstrating the IDOR vulnerability.
Public author profiles and
stories use `/profile/stories?userid=<author-uuid>`; these can be viewed by any
visitor and never include personal files. Bob's downloadable **Top_Secret** file
is stored under `bob_account/__pycache__/Top_Secret`. Alice, Diana, and Eve
also have downloadable story-related files on their private profiles.

## Network challenge

The lab also starts a read-only backup service on TCP port `9000`. Players can
discover it with a port scan, perform the knock, and connect with Netcat:

```text
nc <target> 9000
LIST
GET backup.txt
```

The service accepts only `LIST`, `GET backup.txt`, and `QUIT`. The backup
contains the network challenge flag.
