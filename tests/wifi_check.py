# wifi_check.py - run on the Fob in Thonny.
# Joins the school WiFi using the Fob's config.py, then checks what the
# network allows. It sends NO alert data anywhere. The TCP checks only open a
# connection and close it right away.
#
# Before running: config.py on the Fob must have the WiFi name and password.
# Never paste them into chat, a screenshot or a commit.

import network
import socket
import time

import config

SSID = getattr(config, "WIFI_SSID", None) or getattr(config, "SSID", None)
PASSWORD = getattr(config, "WIFI_PASSWORD", None) or getattr(config, "WIFI_PASS", None) or getattr(config, "PASSWORD", None)

# Laptop IP on the school WiFi, for the port 1883 check. Fill in after the laptop
# joins the same network (ipconfig, "Wireless LAN adapter Wi-Fi", IPv4 Address).
LAPTOP_IP = ""

# A public test server, only to see if outgoing port 1883 is allowed at all.
# Nothing is published to it.
PUBLIC_HOST = "test.mosquitto.org"


def tcp_check(host, port, timeout_s=5):
    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
    except Exception as e:
        return "DNS failed ({})".format(e)
    s = socket.socket()
    s.settimeout(timeout_s)
    try:
        s.connect(addr)
        return "OPEN"
    except Exception as e:
        return "blocked or no answer ({})".format(e)
    finally:
        s.close()


def main():
    if not SSID or not PASSWORD:
        print("config.py has no WiFi name or password. Add WIFI_SSID and WIFI_PASSWORD.")
        return

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        wlan.disconnect()
        time.sleep(1)

    print("Joining the school WiFi ...")
    wlan.connect(SSID, PASSWORD)
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > 20000:
            print("FAIL: could not join within 20 s. Status code:", wlan.status())
            return
        time.sleep(0.5)

    ms = time.ticks_diff(time.ticks_ms(), start)
    ip, mask, gateway, dns = wlan.ifconfig()
    print("Joined in {} ms".format(ms))
    print("  Fob IP:   ", ip)
    print("  Gateway:  ", gateway)
    print("  DNS:      ", dns)
    try:
        print("  Signal:   ", wlan.status("rssi"), "dBm")
    except Exception:
        pass
    try:
        print("  Channel:  ", wlan.config("channel"))
    except Exception:
        pass

    print("\nChecks:")
    print("  Internet DNS (example.com):", tcp_check("example.com", 80))
    print("  Outgoing port 1883 (public test broker):", tcp_check(PUBLIC_HOST, 1883))
    print("  Outgoing port 8883 (MQTT over TLS):", tcp_check(PUBLIC_HOST, 8883))
    if LAPTOP_IP:
        print("  Laptop broker {}:1883:".format(LAPTOP_IP), tcp_check(LAPTOP_IP, 1883))
    else:
        print("  Laptop broker: skipped (LAPTOP_IP is empty)")

    wlan.disconnect()
    print("\nDone. Disconnected.")


main()
