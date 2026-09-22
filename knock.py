"""Open the Common Ground website with its TCP port-knocking sequence."""

import argparse
import socket


KNOCK_PORTS = (7001, 7002, 7003)


def knock(host, ports, timeout):
    for port in ports:
        with socket.create_connection((host, port), timeout=timeout):
            pass


def main():
    parser = argparse.ArgumentParser(description="Knock on the Common Ground ports")
    parser.add_argument("host", nargs="?", default="127.0.0.1")
    parser.add_argument("--timeout", type=float, default=2)
    args = parser.parse_args()
    knock(args.host, KNOCK_PORTS, args.timeout)
    print("Port knock accepted. Open http://{}:8000".format(args.host))


if __name__ == "__main__":
    main()
