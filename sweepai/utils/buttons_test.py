import unittest
import unittest.mock

from sweepai.utils.buttons import (
    Button,
    ButtonList,
    check_button_activated,
    check_button_title_match,
    create_action_buttons,
    create_button,
    get_toggled_state,
)


class TestButtons(unittest.TestCase):
    def test_create_button(self):
        self.assertEqual(create_button("Test", False), "- [ ] Test")
        self.assertEqual(create_button("Test", True), "- [x] Test")

    def test_create_action_buttons(self):
        labels = ["Test1", "Test2"]
        expected_output = "## Actions\n- [ ] Test1\n- [ ] Test2"
        self.assertEqual(create_action_buttons(labels), expected_output)

    def test_get_toggled_state(self):
        changes_request = unittest.mock.Mock()
        changes_request.body_from = "- [x] Test"
        self.assertTrue(get_toggled_state("Test", changes_request))

    def test_check_button_activated(self):
        changes_request = unittest.mock.Mock()
        changes_request.body_from = "- [ ] Test"
        self.assertTrue(check_button_activated("Test", "- [x] Test", changes_request))

    def test_check_button_title_match(self):
        changes_request = unittest.mock.Mock()
        changes_request.body_from = "Test"
        self.assertTrue(check_button_title_match("Test", "Test", changes_request))

    def test_button(self):
        button = Button("Test", True)
        self.assertEqual(str(button), "- [x] Test")

    def test_button_list(self):
        buttons = [Button("Test1", False), Button("Test2", True)]
        button_list = ButtonList("## My Buttons", buttons)
        self.assertEqual(
            button_list.serialize(), "## My Buttons\n- [ ] Test1\n- [x] Test2"
        )
        self.assertEqual(button_list.get_clicked_buttons(), [buttons[1]])


if __name__ == "__main__":
    unittest.main()
