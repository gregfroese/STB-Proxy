import unittest

import accounts


class HashingTest(unittest.TestCase):
    def test_round_trip(self):
        stored = accounts.hashPassword("hunter2")
        self.assertTrue(accounts.verifyPassword("hunter2", stored))

    def test_wrong_password_fails(self):
        stored = accounts.hashPassword("hunter2")
        self.assertFalse(accounts.verifyPassword("hunter3", stored))

    def test_hash_is_self_describing_and_never_plaintext(self):
        stored = accounts.hashPassword("hunter2")
        algorithm, iterations, salt, digest = stored.split("$")
        self.assertEqual(algorithm, "pbkdf2_sha256")
        self.assertEqual(int(iterations), 600000)
        self.assertNotIn("hunter2", stored)
        self.assertTrue(salt)
        self.assertTrue(digest)

    def test_each_hash_uses_a_fresh_salt(self):
        self.assertNotEqual(accounts.hashPassword("same"), accounts.hashPassword("same"))

    def test_a_malformed_hash_is_wrong_not_an_error(self):
        for stored in ("", "nonsense", "md5$1$a$b", "pbkdf2_sha256$abc$a$b", None):
            self.assertFalse(accounts.verifyPassword("x", stored))


class NormaliseTest(unittest.TestCase):
    def test_keeps_well_formed_records(self):
        records = accounts.normaliseAccounts([
            {"username": "katie", "hash": "h", "blocks": ["Kids"], "enabled": True},
        ])
        self.assertEqual(records, [{"username": "katie", "hash": "h", "blocks": ["Kids"], "enabled": True}])

    def test_drops_junk_and_fills_defaults(self):
        records = accounts.normaliseAccounts([
            "nope", {"hash": "h"}, {"username": "", "hash": "h"},
            {"username": "katie", "hash": "h", "blocks": "Kids"},
        ])
        self.assertEqual(records, [{"username": "katie", "hash": "h", "blocks": [], "enabled": True}])

    def test_a_non_list_is_empty(self):
        self.assertEqual(accounts.normaliseAccounts(None), [])
        self.assertEqual(accounts.normaliseAccounts({"username": "katie"}), [])


class TransformTest(unittest.TestCase):
    def test_find_account(self):
        records = [{"username": "katie", "hash": "h", "blocks": [], "enabled": True}]
        self.assertIs(accounts.findAccount(records, "katie"), records[0])
        self.assertIsNone(accounts.findAccount(records, "nope"))

    def test_rename_block_rewrites_every_account(self):
        records = [{"username": "katie", "blocks": ["Kids", "Sports"]}]
        accounts.renameBlock(records, "Kids", "Children")
        self.assertEqual(records[0]["blocks"], ["Children", "Sports"])

    def test_prune_blocks_drops_names_no_block_uses(self):
        records = [{"username": "katie", "blocks": ["Kids", "Gone"]}]
        accounts.pruneBlocks(records, {"Kids"})
        self.assertEqual(records[0]["blocks"], ["Kids"])


if __name__ == "__main__":
    unittest.main()
