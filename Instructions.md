# Challenge Description

#### You were hired as a secret service agent for JBI (Jin's Bureau of Investigation), to lead the investigation on the group of `Cyber Criminals` called *CyberMaxxing group* that is responsible for leaking Lab Quiz answers through an online forum, that was created by his evil twin `Jinvicular` and his clone assistants
You are given a pre-made account of `CuriousDuck228` to investigate their evil plans and find `3 flags` accross this challenge

### Login credentials:
Name: CuriousDuck228
Password: v3rys1!r0ngp2ssw0r8

# Challenge Instructions

Use the server address provided by the challenge host, and access the main website on port `8001`.


## Flag 1

To find `Flag 1` you have to access website on the given `IP` + `8001`.  

- Open the challenge website on port `8001`.

## Flag 2

For the second flag you should retreive some `super secret` file from Jinvicular's profile and investigate it. It seems like this secret file is a compiled binary that holds the second flag.

## Flag 3

You can perform `nmap` on the Target_IP and find other service running on the port range `8000-9000`, it is a bakup service that contains the backup configurations and `flag 3`. However, a [Port Knocker](https://en.wikipedia.org/wiki/Port_knocking) blocks all the attempts to directly access the service. You have to find the correct sequence of `knocks` to open the port 9000. The blog posts from other authors could be useful to find the sequence