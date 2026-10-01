TEST_FUNC(explicit_window_commands_do_not_require_current_focus,
{
    TEST_CHECK(window_command_has_explicit_id("123\0--swap\0west\0\0"), true);
    TEST_CHECK(window_command_has_explicit_id("--focus\0" "123\0--toggle\0float\0\0"), true);
    TEST_CHECK(window_command_has_explicit_id("--focus\0east\0\0"), false);
    TEST_CHECK(window_command_has_explicit_id("--focus\0\0"), false);
    TEST_CHECK(window_command_has_explicit_id("--swap\0" "123\0\0"), false);
    TEST_CHECK(window_command_has_explicit_id("--toggle\0float\0\0"), false);
    TEST_CHECK(window_selector_is_explicit_id("123\0\0"), true);
    TEST_CHECK(window_selector_is_explicit_id("east\0\0"), false);
    TEST_CHECK(window_selector_is_explicit_id("\0"), false);
});
