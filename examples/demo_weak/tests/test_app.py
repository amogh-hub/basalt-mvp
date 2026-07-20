import unittest
from app import is_adult


class AppTests(unittest.TestCase):
    def test_adult_happy_path_only(self):
        self.assertTrue(is_adult(20))


if __name__ == "__main__":
    unittest.main()
