from __future__ import annotations

import threading
import unittest

from nothing_here.app import acquire_instance


class SingleInstanceTests(unittest.TestCase):
    def test_a_second_acquire_fails_until_the_first_is_released(self) -> None:
        name = "Local\\NothingHereTestSerial"
        first = acquire_instance(name)
        self.assertIsNotNone(first)
        assert first is not None
        try:
            self.assertIsNone(acquire_instance(name))
        finally:
            first.close()
        again = acquire_instance(name)
        self.assertIsNotNone(again)
        assert again is not None
        again.close()

    def test_two_overlapping_acquires_leave_one_winner(self) -> None:
        name = "Local\\NothingHereTestRace"
        barrier = threading.Barrier(2)
        found: list[object] = []

        def grab() -> None:
            barrier.wait()
            found.append(acquire_instance(name))

        threads = [threading.Thread(target=grab) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [item for item in found if item is not None]
        self.assertEqual(len(winners), 1)
        winners[0].close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
