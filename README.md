# CITS3006 Penetration Testing

## 1. Lab Contents

This lab includes following vulnerabilities:
Flag 1: IDOR Vulnerability (Horizontal privelege escalation)
Flag 2: Reverse enginering
Flag 3: exposed backup-service with Port Knocker

## 2. Flag 1: IDOR vulnerability

### Step by step walkthrough

#### Discovering Bob'd UUID
The public Authors page displays the UUID used by each author profile. We can get all the authors with the corresponding information, then match the pattern `jinvicular` and get Jin's UUID. It can be done 2 ways:

##### 1. Using powershell:
```bash
authors=$(curl -s http://Target_IP:8001/authors)
echo "$authors" | grep -A 2 'jinvicular'
```

It should print out something like this:
```bash
...<a class="read-link" href="/profile/stories?userid=06ac561c-7086-497d-a3e8-67467c6c4caf">...
```
With the UUID that we are looking for:\
**06ac561c-7086-497d-a3e8-67467c6c4caf**
##### 2. Directly from the public HTML:

    - Navigate to the authors screen
    - From authors screen navigate to Jin's profile
    - You can copy from the URL bar exposed Bob's userID that is used to identify each user.

### 2.2 Log in as a given user

The IDOR requires authentication, but it does not require the account being requested to match the logged-in account. 

#### Login as CuriousDuck228:
name: CuriousDuck228 \
pwd: v3rys1!r0ngp2ssw0r8

Then navigate to the profile screen, where we can see our own uuid in the URL tab:

```powershell
/users/user?userid=c35ea621-721f-4b2c-8093-a10905692e4d
```
### 2.3 Request Jin's private profile while logged in as CuriousDuck228

With saved Jin's UUID from previous step, we change the `userid` directly in URL, which send a request a renders Jin's private profile, where we can see his private files and the flag:
```
FLAG{Bob_7hE_BUiLDerFL@9}
```
The application checks only that a session exists. It does not check that the
requested `userid` belongs to the logged-in user. Therefore, it allowes us to request the Jin's session even though we are logged in as a different user.

## 3. Flag 2 Reverse Engeneering

From Jinvicular's private profile, download the `Top_Secret` file.
We are able to download `Top_Secret` file that is a linux ELF executable. We can run it to see what exactly it does.

```
./Top_Secret
```
Or
```powershell
wsl -- ./Top_Secret
```
After executing the file we see next message asking for the password:
```
hello enter the password:
```

### 3.1 Load the binary in IDA or Ghidra

After loading it into a decompiler locate the `main` and identify the sequence of function calls:
printf(hello...) -> fgets(u_input) -> unnamed_function(check_pwd) -> conditional_branch(correct/incorrect)
### 3.2 Password check function
We can see that the function checks the lengh of the password using `strlen` and it checks it against *13*, therefore, password length is 13.
Then the loop over an input bytes applying some math operations.
Then comparison of transformed bytes against an arr stored at `.rodata`
### 3.3 Back transformation
Since we know the forward transformation of the bits in the array we have to write a script that will reverse the transformation of the bits in the array.

```python
enc=[extracted bytes from .rodata]
password = bytes(invert(b, i) for i, b in enumerate(enc))
print(password)
```

After running the code above with the extracted data, we get the following pwd `Sup3rR3v3rs3!`, and after putting this password we get the flag.

```text
FLAG{th1s_!s_s3cre11t_f16g}
```

## 3. Flag 3 backup-service flag

### 3.1 Perform the port knock

For the Port Knocker flag, student know that the correct sequence of the ports is `8002`, `8003`, `8004`, therefore we need to write the program that will knock on the ports in a correct sequence with less than 5 seconds delay `OR` alternatively use `knocker` on those ports and that will unlock the backup-service.

Knocker:
```bash
knocker -H 192.168.56.101 -SP 8002 -EP 8004
```

`-H` specifies Host \
`-SP` start port \
`-EP` end port

If port knock was successful you will see the following text:

```text
Port knock accepted. Open http://Target_IP:8001
```

The knock unlocks the backup service for 180 seconds for the source address.

### 3.2 Connect to TCP port 9000

You can use Netcat if installed, run:

```bash
nc Target_IP 9000
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
ncat Target_IP 9000
```