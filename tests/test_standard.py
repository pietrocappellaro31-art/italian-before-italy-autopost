import sys
import pathlib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "build"))
import daily_build  # noqa: E402

GOOD = {"caption": "Voiced by Pietro, a native speaker.", "beats": [
    {"kind": "hook", "sub": "Pietro, a native speaker", "vo": "Listen.", "pics": ["coffee"], "particles": "beans"},
    {"kind": "listen", "pics": ["coffee"], "particles": "beans"},
    {"kind": "quiz", "vo": "Quick quiz.", "options": ["a", "b"], "option_icons": ["coffee", "plate"],
     "particles": "beans"},
    {"kind": "turn", "vo": "Your turn.", "particles": "beans"},
    {"kind": "cta", "vo": "Save it.", "particles": "beans"}]}


class Standard(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(daily_build.lint_reel_standard(GOOD), [])

    def test_missing_pics_name_vo_and_italian_vo_fail(self):
        import copy
        bad = copy.deepcopy(GOOD)
        bad["caption"] = "x"
        del bad["beats"][1]["pics"]
        bad["beats"][3]["vo"] = "Say grazie"
        del bad["beats"][4]["vo"]
        p = "\n".join(daily_build.lint_reel_standard(bad))
        for s in ("Pietro", "no pics", "grazie", "no English narration"):
            self.assertIn(s, p)


if __name__ == "__main__":
    unittest.main()
