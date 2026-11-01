import unittest

from calculator import add


class CalculatorTests(unittest.TestCase):
    def test_add_positive(self) -> None:
        self.assertEqual(add(2, 3), 5)

    def test_add_negative(self) -> None:
        self.assertEqual(add(-4, 1), -3)


if __name__ == "__main__":
    unittest.main()
