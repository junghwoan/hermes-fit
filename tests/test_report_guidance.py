"""Public-skill report contract checks, not live-model efficacy tests."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReportGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.skill = (ROOT / 'skills/hermes-fit/SKILL.md').read_text()

    def test_empty_proposals_do_not_request_approval(self):
        self.assertIn('When there are no instruction-change proposals', self.skill)
        self.assertIn('nothing to approve or apply', self.skill)
        self.assertIn('do not offer a proposal number, preview or approval request', self.skill)
        self.assertIn('Ask for explicit live user approval of the exact digest', self.skill)

    def test_existing_instruction_cause_is_a_hypothesis_not_new_rule(self):
        self.assertIn('existing applicable instruction was not followed', self.skill)
        self.assertIn('hypothesis in the first report', self.skill)
        self.assertIn('cite the selected evidence', self.skill)
        self.assertIn('rather than adding a duplicate rule', self.skill)
        self.assertIn('do not claim the cause is proven or execution repaired', self.skill)
        self.assertIn('obey their native gates', self.skill)


if __name__ == '__main__':
    unittest.main()
