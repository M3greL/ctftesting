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

Open <http://127.0.0.1:8000>. The home page is public and contains one food post
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

The lab also starts an unauthenticated, read-only backup service on TCP port
`9001`. Players can discover it with a port scan and connect with Netcat:

```text
nc <target> 9001
LIST
GET backup.txt
```

The service accepts only `LIST`, `GET backup.txt`, and `QUIT`. The backup
contains the network challenge flag.
