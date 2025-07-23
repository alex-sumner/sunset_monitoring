import hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
# eth_utils keccak is SHA3-256 (Keccak-256) which Ethereum uses
from eth_utils import encode_hex, keccak as eth_keccak

# Your provided public key string, confirmed as secp256k1
YOUR_SECP256K1_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAEGY/6A6/+AtvhJFaJ2XZeo7VDg2TKKh4g
c6JfWB1J5k+xIyyWK2LE6pfXghqSfcM7dab4h6eB/nPxUpsUdekxxg==
-----END PUBLIC KEY-----"""

OLD_KEY_1 = """-----BEGIN PUBLIC KEY-----
MFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAE5G/gvjg0TkHfeMXxs2a5HkVqdQYOtgf2
18pA+Zf9j8lIrxIYQ5W+Xf2tEql7X8GhmIYvMV4X6Y7b7gGBO6IE5Q==
-----END PUBLIC KEY-----"""

OLD_KEY_2 = """-----BEGIN PUBLIC KEY-----
MFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAEKph+GGUGWLoS6pu63TuJmghC/7Mlw9P/
W7LY0JkYXSAIHmr/mYfo+vUU+j1oUGlKxyYUlUTX5f79BWyR4ny0Zg==
-----END PUBLIC KEY-----"""

def derive_ethereum_address(pem_public_key_string: str) -> str:
    """
    Derives the Ethereum address from a PEM-encoded secp256k1 public key.

    Args:
        pem_public_key_string: The public key string in PEM format.
                               Must be a secp256k1 curve key.

    Returns:
        The derived Ethereum address as a hex string (e.g., '0x...').

    Raises:
        ValueError: If the key is not an EC key, not secp256k1, or parsing fails.
    """
    try:
        # 1. Load the PEM public key using cryptography library
        public_key = serialization.load_pem_public_key(
            pem_public_key_string.encode('utf-8'),
            backend=default_backend()
        )
    except Exception as e:
        raise ValueError(f"Failed to load PEM public key: {e}")

    # 2. Verify it's an Elliptic Curve key
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise ValueError("Provided key is not an Elliptic Curve public key.")

    # 3. Confirm the curve is secp256k1 (this check should now pass based on your openssl output)
    if not isinstance(public_key.curve, ec.SECP256K1):
        raise ValueError(
            f"Public key curve is '{public_key.curve.name}', but Ethereum requires 'secp256k1'."
        )

    # 4. Get the raw uncompressed public key bytes (0x04 || X || Y)
    #    Using X962 encoding and Raw format for compatibility with newer cryptography versions.
    #    This will still produce the 0x04-prefixed uncompressed point.
    public_key_bytes_with_prefix = public_key.public_bytes(
        encoding=serialization.Encoding.X962, # Corrected: Use X962 instead of UncompressedPoint
        format=serialization.PublicFormat.UncompressedPoint # Keep this format, but use X962 encoding
    )
    # Note: For some versions/formats, PublicFormat.Raw might be used, but UncompressedPoint
    # combined with X962 encoding specifically requests the 0x04-prefixed uncompressed point.

    # 5. Remove the 0x04 prefix to get the 64-byte raw public key (X || Y)
    # The '04' prefix indicates uncompressed format as per SECP256k1 standards.
    raw_ethereum_public_key = public_key_bytes_with_prefix[1:] # Slice off the 0x04 byte

    # Verify the length, should be 64 bytes (32 for X, 32 for Y)
    if len(raw_ethereum_public_key) != 64:
        raise ValueError(f"Extracted raw public key has unexpected length: {len(raw_ethereum_public_key)} bytes. Expected 64 bytes.")

    # 6. Compute the Keccak-256 hash of the raw 64-byte public key
    # Ethereum uses Keccak-256, not SHA-256. eth_utils.keccak is the correct one.
    public_key_hash = eth_keccak(raw_ethereum_public_key)

    # 7. Take the last 20 bytes of the hash to get the Ethereum address
    ethereum_address_bytes = public_key_hash[-20:]

    # 8. Convert to hex string with '0x' prefix
    ethereum_address = encode_hex(ethereum_address_bytes)

    return ethereum_address

# --- Execution ---
if __name__ == "__main__":
    try:
        address = derive_ethereum_address(YOUR_SECP256K1_PUBLIC_KEY_PEM)
        print(f"The Ethereum Address for your public key is: {address}")
        address = derive_ethereum_address(OLD_KEY_1)
        print(f"The Ethereum Address for old key 1 is: {address}")
        address = derive_ethereum_address(OLD_KEY_2)
        print(f"The Ethereum Address for old key 2 is: {address}")
    except ValueError as e:
        print(f"Error deriving Ethereum address: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
