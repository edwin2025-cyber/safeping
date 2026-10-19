"""Registers a device and prints its secret key.

  python add_device.py FOB-001 "Student Name"
  python add_device.py REF-01 --role REF

Put the printed key in that device's config.py. Keep it private."""
import argparse
import secrets

import db


def main():
    parser = argparse.ArgumentParser(description="Register a SafePing device")
    parser.add_argument("device_id")
    parser.add_argument("student_name", nargs="?", default=None)
    parser.add_argument("--role", choices=["FOB", "REF"], default="FOB")
    parser.add_argument("--key", help="use this key instead of making a new one")
    args = parser.parse_args()

    if args.role == "FOB" and not args.student_name:
        parser.error("a Fob needs a student name")

    db.init_db()
    key = args.key or secrets.token_hex(16)
    db.add_device(args.device_id, args.role, args.student_name, key)
    print("Registered {} ({})".format(args.device_id, args.role))
    print("Secret key: {}".format(key))


if __name__ == "__main__":
    main()
