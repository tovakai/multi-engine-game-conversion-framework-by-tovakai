# Synthetic TLS fixtures

`ca.pem` is a test-only CA. `server.pem` is its localhost server certificate,
with SAN `DNS:localhost`; `server.key` is the deliberately public test private
key. Never use these keys or certificates for a real service. The CA signing
key is not included. Tests use MemoryBIO handshakes with no sockets or CDN.
Certificates expire in October 2036; regenerate before then with RSA-2048,
critical CA basicConstraints/keyCertSign/cRLSign, and serverAuth/localhost SAN.
Update the subject-hash fixture filename in `test_tls.py` if the CA name changes.
