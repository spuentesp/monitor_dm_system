"""Tests for monitor_data.interop.card_macros."""

from monitor_data.interop.card_macros import DEFAULT_USER_NAME, substitute_card_macros


class TestSubstituteCardMacros:
    def test_replaces_char_and_user(self):
        text = "{{char}} is a ranger who trusts {{user}} with her life."
        out = substitute_card_macros(text, char_name="Elara", user_name="Kael")
        assert out == "Elara is a ranger who trusts Kael with her life."

    def test_user_falls_back_to_default(self):
        out = substitute_card_macros("Hello, {{user}}!", char_name="Elara")
        assert out == f"Hello, {DEFAULT_USER_NAME}!"

    def test_blank_user_name_falls_back(self):
        out = substitute_card_macros("Hi {{user}}", char_name="Elara", user_name="  ")
        assert out == f"Hi {DEFAULT_USER_NAME}"

    def test_case_insensitive(self):
        out = substitute_card_macros(
            "{{CHAR}} meets {{User}}", char_name="Elara", user_name="Kael"
        )
        assert out == "Elara meets Kael"

    def test_inner_whitespace_tolerated(self):
        out = substitute_card_macros("{{ char }} / {{  user  }}", char_name="E", user_name="K")
        assert out == "E / K"

    def test_legacy_angle_aliases(self):
        out = substitute_card_macros("<CHAR> greets <user>", char_name="Elara", user_name="Kael")
        assert out == "Elara greets Kael"

    def test_repeated_placeholders_all_replaced(self):
        out = substitute_card_macros(
            "{{char}} thinks about {{char}}'s past.", char_name="Elara"
        )
        assert out == "Elara thinks about Elara's past."

    def test_empty_and_plain_text_passthrough(self):
        assert substitute_card_macros("", char_name="Elara") == ""
        plain = "No macros here."
        assert substitute_card_macros(plain, char_name="Elara") == plain

    def test_unknown_macros_untouched(self):
        out = substitute_card_macros("{{random}} {{char}}", char_name="Elara")
        assert out == "{{random}} Elara"
