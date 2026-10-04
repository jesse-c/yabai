TEST_FUNC(stale_window_notifications_do_not_access_freed_or_reused_windows, {
    struct table saved = g_window_manager.window;
    table_init(&g_window_manager.window, 8, hash_wm, compare_wm);

    struct window *window = calloc(1, sizeof(*window));
    window->id = 123;
    window->generation = 1;
    window->id_ptr = &window->id;
    window_manager_add_window(&g_window_manager, window);
    void *context = window_notification_context(window);
    TEST_CHECK(window_from_notification(context) == window, true);

    window_manager_remove_window(&g_window_manager, window->id);
    free(window);
    TEST_CHECK(window_from_notification(context) == NULL, true);
    EVENT_HANDLER_WINDOW_MINIMIZED(context, 0);
    EVENT_HANDLER_WINDOW_DEMINIMIZED(context, 0);
    EVENT_HANDLER_WINDOW_DESTROYED(context, 0);

    struct window *replacement = calloc(1, sizeof(*replacement));
    replacement->id = 123;
    replacement->generation = 2;
    replacement->id_ptr = &replacement->id;
    window_manager_add_window(&g_window_manager, replacement);
    TEST_CHECK(window_from_notification(context) == NULL, true);
    TEST_CHECK(window_from_notification(window_notification_context(replacement)) == replacement, true);
    EVENT_HANDLER_WINDOW_MINIMIZED(context, 0);
    EVENT_HANDLER_WINDOW_DEMINIMIZED(context, 0);
    EVENT_HANDLER_WINDOW_DESTROYED(context, 0);
    TEST_CHECK(window_manager_find_window(&g_window_manager, 123) == replacement, true);
    TEST_CHECK(replacement->flags, 0);

    window_manager_remove_window(&g_window_manager, replacement->id);
    free(replacement);
    table_free(&g_window_manager.window);
    g_window_manager.window = saved;
})
