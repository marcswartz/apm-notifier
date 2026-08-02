import unittest

from apm_notifier.filtering import RoleFilter


class RoleFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = RoleFilter(2027, (2024, 2025, 2026))

    def test_accepts_target_roles(self) -> None:
        accepted = (
            "Associate Product Manager — 2027 Start",
            "Rotational Product Manager",
            "Product Manager Intern, Summer 2027",
            "Intern - Product Management",
            "Technical Product Manager Co-op",
            "Product Marketing Intern",
            "Product Marketing Manager Internship — Summer 2027",
        )
        for title in accepted:
            with self.subTest(title=title):
                self.assertTrue(self.filter.matches(title))

    def test_rejects_unrelated_or_old_roles(self) -> None:
        rejected = (
            "Senior Product Manager",
            "Product Marketing Manager",
            "Software Engineering Intern",
            "Associate Project Manager",
            "Product Manager Intern — Summer 2026",
            "Director, Associate Product Manager Program",
        )
        for title in rejected:
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title))

    def test_accepts_allowed_locations(self) -> None:
        accepted = (
            "Seattle, WA, US",
            "Toronto, Ontario, Canada",
            "London, England, United Kingdom",
            "Remote - USA",
            "Vancouver, BC / Singapore",
        )
        for location in accepted:
            with self.subTest(location=location):
                self.assertTrue(self.filter.matches_location(location))

    def test_rejects_disallowed_or_ambiguous_locations(self) -> None:
        rejected = (
            "SG, Singapore",
            "CN, 31, Shanghai",
            "Bengaluru, Karnataka, India",
            "Remote",
            "Worldwide",
            "",
        )
        for location in rejected:
            with self.subTest(location=location):
                self.assertFalse(self.filter.matches_location(location))

    def test_can_read_location_from_a_title(self) -> None:
        self.assertTrue(self.filter.matches_location("", "Product Manager Intern — New York"))
        self.assertFalse(self.filter.matches_location("", "Product Manager Intern — Singapore"))


if __name__ == "__main__":
    unittest.main()
