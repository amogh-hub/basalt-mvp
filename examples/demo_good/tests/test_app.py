import unittest
from app import add, is_adult


class AppTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_is_adult_boundary(self):
        self.assertTrue(is_adult(18))
        self.assertFalse(is_adult(17))


if __name__ == "__main__":
    unittest.main()
