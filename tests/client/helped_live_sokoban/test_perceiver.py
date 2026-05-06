import unittest

from client.helped_live_sokoban.perceiver import HelpedPerceiver


class HelpedPerceiverTests(unittest.TestCase):
    def test_maps_raw_frame_to_puzzlescript_symbols(self) -> None:
        perceiver = HelpedPerceiver()

        frame = perceiver.from_grid([[0, 1, 2, 3, 4, 5]])

        self.assertEqual(frame.to_rows(), [".#P*@O"])

    def test_does_not_invent_base_layer_tokens(self) -> None:
        perceiver = HelpedPerceiver()

        frame = perceiver.from_grid([[1, 4]])

        self.assertEqual(frame.cell(0, 0), "#")
        self.assertEqual(frame.cell(1, 0), "@")
        self.assertNotIn("base_", " ".join(frame.to_rows()))


if __name__ == "__main__":
    unittest.main()
