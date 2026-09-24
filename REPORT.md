# CITS3006 Penetration Testing


Three Flags
1. `FLAG{th1s_!s_s3cre11t_f16g}`
2. `FLAG{c1tsE006_no1_s3cr4t_4lag}`
3. `FLAG{Bob_7hE_BUiLDerFL@9}`

Do not expose the service to an untrusted network while following these steps;
the application is intentionally vulnerable.

## 1. Start the lab


## 2. Flag 1: IDOR vulnerability


### Step by step walkthrough

#### Discovering Bob'd UUID
The public Authors page displays the UUID used by each author profile. We can get all the authors with the corresponding information, then match the pattern Bob and get Bob's UUID. It can be done 2 ways:

##### 1. Using powershell:
```bash
authors=$(curl -s http://127.0.0.1:8001/authors)
echo "$authors" | grep -A 2 'Bob'
```

It should print out something like this:
```bash
...<a class="read-link" href="/profile/stories?userid=06ac561c-7086-497d-a3e8-67467c6c4caf">...
```
With the UUID that we are looking for:\
**06ac561c-7086-497d-a3e8-67467c6c4caf**
##### 2. Directly from the public HTML:

    - Navigate to the authors screen
    - From authors screen navigate to Bob's profile
    - You can copy from the URL bar exposed Bob's userID that is used to identify each user.

### 2.2 Log in as a given user Alice

The IDOR requires authentication, but it does not require the account being requested to match the logged-in account. 

#### Login as Alice:
name: Alice \
pwd: Alicepass

Then navigate to the profile screen, where we can see the uuid of Alice in the URL tab:

```powershell
/users/user?userid=c35ea621-721f-4b2c-8093-a10905692e4d
```
### 2.3 Request Bob's private profile while logged in as Alice

With saved Bob's UUID from previous step, we change the `userid` to a Bob's UUID directly in URL, which send a request a renders Bob's private profile, where we can see his private files and the flag:
```
FLAG{Bob_7hE_BUiLDerFL@9}
```
The application checks only that a session exists. It does not check that the
requested `userid` belongs to the logged-in user. Therefore, it allowes us to request the Bob's session even though we are logged in as Alice.

## 3. *Flag 2* Reverse Engeneering

After gaining the access to the Bob's account we can see the files that he owns, and one of them is called `Top_Secret`.
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




After entering the correct password `Sup3rR3v3rs3!` the executable prints:

```text
FLAG{th1s_!s_s3cre11t_f16g}
```

## 3. Flag 3 backup-service flag

### 3.1 Perform the port knock

For the Port Knocker flag, student know that the correct sequence of the ports is `8002`, `8003`, `8004`, therefore we need to write the program that will knock on the ports in a correct sequence with less than 5 seconds delay `OR` alternatively use `nmap` on those ports and that will unlock the backup-service
If port knock was successful you will see the following text:

```text
Port knock accepted. Open http://127.0.0.1:8001
```

The knock unlocks the backup service for 180 seconds for the source address.

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