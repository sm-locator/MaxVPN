from backend.models.key_pair import KeyPair


def test_key_pair_contains_private_key():
    pair = KeyPair(
        private_key="private",
        public_key="public",
    )

    assert pair.private_key == "private"


def test_key_pair_contains_public_key():
    pair = KeyPair(
        private_key="private",
        public_key="public",
    )

    assert pair.public_key == "public"
