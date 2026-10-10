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
            "Product Development Internship Program (Summer 2027)",
            "Creative Product Manager Graduate (Creative and Brand Innovation) - 2027 Start",
            "Graduate Product Manager — 2027 Start",
            "Product Manager: New Grad Accelerator",
            "Product Manager, New Grad (2027 Start)",
            "Early Career, Associate Product Manager (2027)",
            "Graduate Programme 2027: Product Owner (UX)",
            "Graduate Programme 2027: Product Owner (Technical)",
            "Internship Programme 2027: Product Owner (UX)",
            "Apprentice Product Manager",
            "Associate Product Builder",
            "Junior Product Manager - Product Management",
            "Entry-Level Product Owner",
            "Early Career Product Manager",
            "Early–Career Product Manager",
            "Product Manager I",
            "Rotational Product Management Program - Fall 2027",
            "Graduate Product Owner - Spring 2027",
            "Global Product Strategy & Operation Graduate (Scaled Growth) - 2027 Start",
            "Product Solutions and Operations Graduate (Commerce Ads) - 2027 Start",
            "Product Marketing Manager Graduate - 2027 Start",
            "Associate, Product Operations",
            "Junior Product Strategy Analyst",
            "Product Growth Intern - Summer 2027",
            "New–Grad Product Solutions Analyst",
            "Product Manager Graduate (Design Systems) - 2027 Start",
        )
        for title in accepted:
            with self.subTest(title=title):
                self.assertTrue(self.filter.matches(title))

    def test_rejects_unrelated_or_old_roles(self) -> None:
        rejected = (
            "Senior Product Manager",
            "Senior Product Manager: New Grad Accelerator",
            "Product Manager: New Grad Accelerator 2026",
            "Product Marketing Manager",
            "Software Engineering Intern",
            "Associate Project Manager",
            "Product Manager Intern — Summer 2026",
            "Product Marketing Intern — Winter 2027",
            "Director, Associate Product Manager Program",
            "Senior Product Owner",
            "Graduate Software Engineer - Product Team",
            "Product Designer - New Grad",
            "Product Manager II",
            "Graduate Programme 2026: Product Owner (UX)",
            "Product Owner Intern - Winter 2027",
            "Senior Product Operations Graduate - 2027 Start",
            "Product Solutions Engineer Graduate - 2027 Start",
            "New Grad Product Growth Data Scientist",
            "Product Operations Manager",
        )
        for title in rejected:
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title))

    def test_growth_product_roles_are_opt_in_for_selected_companies(self) -> None:
        accepted = (
            "Growth Product Manager",
            "Product Manager, Growth",
            "Product Manager, Multi-Cloud Growth - Google",
        )
        for title in accepted:
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title))
                self.assertTrue(
                    self.filter.matches(title, include_growth_product_roles=True)
                )

        self.assertFalse(
            self.filter.matches(
                "Senior Growth Product Manager",
                include_growth_product_roles=True,
            )
        )

    def test_product_specialists_are_enabled_by_default_and_exclude_senior_roles(self) -> None:
        for title in ("Specialist, Global Product Management", "Product Management Analyst", "Product Specialist"):
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title, include_product_specialists=False))
                self.assertTrue(self.filter.matches(title))
        for title in ("Senior Specialist, Global Product Management", "Lead Product Specialist", "Sales Specialist", "Product Manager"):
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title, include_product_specialists=True))

    def test_adjacent_marketing_is_opt_in_and_limited_to_early_career(self) -> None:
        accepted = (
            "Marketing Intern — Summer 2027",
            "Partner Marketing Specialist",
            "Marketing Associate",
            "Analyst, NA Growth Marketing",
            "Graduate Field Marketing Coordinator — 2027 Start",
            "Dine-In Campaign Graduate - 2027 Start",
            "Account Manager Graduate (Global Business Solutions) - 2027 Start",
            "Graduate Advertising Strategist - 2027 Start",
            "New Grad Growth Analyst - 2027 Start",
            "Early Career Campaign Coordinator",
            "Marketing Manager Graduate - 2027 Start",
        )
        for title in accepted:
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title))
                self.assertTrue(self.filter.matches(title, include_adjacent_marketing=True))

        rejected = (
            "Marketing Intern — Spring 2027",
            "Senior Partner Marketing Specialist",
            "Associate Manager, Integrated Marketing",
            "Strategic Sourcing Specialist - Marketing",
            "Associate Managing Consultant, Advisors & Consulting Services, Marketing",
            "Product Marketing Manager",
            "Account Manager",
            "Campaign Manager",
            "Senior Account Manager Graduate - 2027 Start",
            "Dine-In Campaign Graduate - 2026 Start",
            "Growth Software Engineer Graduate - 2027 Start",
            "Ads Designer Graduate - 2027 Start",
            "Graduate Financial Accountant",
            "Graduate Sales Engineer - Growth",
            "Advertising Intern - Winter 2027",
            "Content Design Intern (Monetization Ads) - 2027 Summer",
            "Design System Design Intern (Monetization Ads) - 2027 Summer",
            "Product Design Intern (Monetization Ads) - 2027 Summer",
            "Data Engineering Project Intern (Ads Targeting) - 2027 Summer",
        )
        for title in rejected:
            with self.subTest(title=title):
                self.assertFalse(self.filter.matches(title, include_adjacent_marketing=True))

    def test_accepts_allowed_locations(self) -> None:
        accepted = (
            "Seattle, WA, US",
            "Toronto, Ontario, Canada",
            "London, England, United Kingdom",
            "Remote - USA",
            "Vancouver, BC / Singapore",
            "McLean, VA / Plano, TX",
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

    def test_rejects_masters_only_graduate_qualification(self) -> None:
        details = """
        Minimum Qualifications:
        Individuals who are completing or have recently completed a Master's degree
        in Business or a related discipline.
        Preferred Qualifications: Experience with creative products.
        """
        self.assertFalse(self.filter.allows_bachelors(details))

    def test_accepts_bachelor_eligible_graduate_qualification(self) -> None:
        details = """
        Minimum Qualifications:
        Individuals completing a Bachelor's degree or Master's degree in Business.
        Preferred Qualifications: Experience with creative products.
        """
        self.assertTrue(self.filter.allows_bachelors(details))

    def test_education_verification_covers_all_graduate_role_families(self) -> None:
        for title in (
            "Dine-In Campaign Graduate - 2027 Start",
            "Account Manager Graduate (GBS) - 2027 Start",
            "Product Solutions and Operations New–Grad",
            "Product Marketing Intern - MBA",
            "Product Management Intern (PhD)",
        ):
            with self.subTest(title=title):
                self.assertTrue(self.filter.is_graduate_role(title))
        self.assertFalse(self.filter.is_graduate_role("Product Manager - Master Data"))
        self.assertFalse(self.filter.is_graduate_role("Associate Product Manager"))

    def test_rejects_explicit_postgraduate_minimums(self) -> None:
        rejected = (
            "Minimum Qualifications: Completing a Master’s degree in Business.",
            "<h3>Minimum Qualifications</h3><ul><li>Master&#39;s degree in business.</li></ul>",
            "Minimum Qualifications: MBA required.",
            "Required Qualifications: Ph.D. in computer science.",
            "Basic Qualifications: MSc in marketing.",
            "Minimum Qualifications: Bachelor's degree and an MBA required.",
            "Minimum Qualifications: <li>Bachelor's degree.</li><li>Master's degree required.</li>",
            "Minimum Qualifications: BS or MS and a PhD required.",
            "Must have a master's degree in business.",
        )
        for details in rejected:
            with self.subTest(details=details):
                self.assertFalse(self.filter.allows_bachelors(details))

    def test_accepts_degree_alternatives_and_optional_advanced_degrees(self) -> None:
        accepted = (
            "Minimum Qualifications: Bachelor’s or Master’s degree in business.",
            "Minimum Qualifications: BS/MS in computer science.",
            "Minimum Qualifications: B.S. or M.S. in computer science.",
            "Minimum Qualifications: Master's or Bachelor's degree in business.",
            "Minimum Qualifications: Bachelor's degree required, MBA preferred.",
            "Minimum Qualifications: Bachelor's degree. Preferred Qualifications: MBA.",
            "<h3>Minimum Qualifications</h3><li>Bachelor’s degree.</li><h3>Preferred Qualifications</h3><li>PhD.</li>",
            "Minimum Qualifications: Bachelor's or higher degree in business.",
            "Minimum Qualifications: Bachelor's degree or above. Proficiency with MS Office required.",
            "Minimum Qualifications: Bachelor's degree or above. Proficiency with MS Excel required.",
            "Minimum Qualifications: Bachelor's degree. Experience with M.S. Office required.",
        )
        for details in accepted:
            with self.subTest(details=details):
                self.assertTrue(self.filter.allows_bachelors(details))

    def test_postgraduate_cohort_titles_override_generic_bachelor_text(self) -> None:
        for title in ("Product Marketing Intern - MBA", "Product Manager Graduate (PhD)"):
            with self.subTest(title=title):
                self.assertFalse(self.filter.allows_bachelors("Minimum Qualifications: Bachelor's degree.", title=title))
        self.assertTrue(self.filter.allows_bachelors("Minimum Qualifications: BS/MS degree.", title="Product Graduate - BS/MS"))
        self.assertTrue(self.filter.allows_bachelors("Minimum Qualifications: Bachelor's degree.", title="Product Graduate - MS Dynamics"))


if __name__ == "__main__":
    unittest.main()
