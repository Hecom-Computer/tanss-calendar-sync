#!/usr/bin/env python3
"""Erzeugt ein lokales Zertifikat fuer die Windows-Server-Installation.

Der private Schluessel verbleibt in ``graph.pem`` auf dem Server. Nur
``graph-public.cer`` darf in Microsoft Entra ID hochgeladen werden.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--days", type=int, default=1095)
    args = parser.parse_args()

    if args.days < 1:
        raise SystemExit("--days muss mindestens 1 sein.")

    directory = args.directory.resolve()
    private_path = directory / "graph.pem"
    public_path = directory / "graph-public.cer"
    if private_path.exists() or public_path.exists():
        raise SystemExit(
            "Zertifikatsdatei existiert bereits. Nichts wurde ueberschrieben: "
            f"{private_path} bzw. {public_path}"
        )

    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "tanss-calendar-sync")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=args.days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        + certificate.public_bytes(serialization.Encoding.PEM)
    )
    public_der = certificate.public_bytes(serialization.Encoding.DER)
    public_path.write_bytes(public_der)

    thumbprint = hashlib.sha1(public_der).hexdigest().upper()
    print(f"Oeffentliches Zertifikat zum Hochladen: {public_path}")
    print(f"Fingerabdruck: {thumbprint}")
    print(f"Gueltig bis: {certificate.not_valid_after_utc:%Y-%m-%d}")


if __name__ == "__main__":
    main()
