TEST_FUNC(event_queue_preserves_backlog_and_detached_batches, {
    struct event_loop loop = {0};
    TEST_CHECK(event_loop_init(&loop), true);
    for (int i = 0; i < 40000; ++i) {
        event_loop_post(&loop, WINDOW_FOCUSED, (void *)(uintptr_t)123, i);
    }
    struct event *batch = event_loop_take(&loop, false);
    event_loop_post(&loop, WINDOW_FOCUSED, NULL, 40000);
    int count = 0;
    while (batch) {
        struct event *next = batch->next;
        TEST_CHECK(batch->param1, count);
        TEST_CHECK(batch->type, WINDOW_FOCUSED);
        TEST_CHECK(batch->context == (void *)(uintptr_t)123, true);
        ++count;
        free(batch);
        batch = next;
    }
    TEST_CHECK(count, 40000);
    batch = event_loop_take(&loop, false);
    TEST_CHECK(batch && batch->param1 == 40000 && !batch->next, true);
    free(batch);
    TEST_CHECK(event_loop_take(&loop, false) == NULL, true);
    pthread_cond_destroy(&loop.ready);
    pthread_mutex_destroy(&loop.lock);
})

struct queue_test_producer {
    struct event_loop *loop;
    uintptr_t id;
};

static void *queue_test_post(void *context)
{
    struct queue_test_producer *producer = context;
    for (int i = 0; i < 20000; ++i) {
        event_loop_post(producer->loop, WINDOW_FOCUSED, (void *)producer->id, i);
    }
    event_loop_post(producer->loop, MENU_CLOSED, (void *)producer->id, 20000);
    return NULL;
}

TEST_FUNC(event_queue_preserves_concurrent_producers_and_wakeups, {
    struct event_loop loop = {0};
    TEST_CHECK(event_loop_init(&loop), true);
    pthread_t threads[3];
    struct queue_test_producer producers[3];
    int counts[3] = {0};
    int finished = 0;
    for (int i = 0; i < 3; ++i) {
        producers[i].loop = &loop;
        producers[i].id = i;
        TEST_CHECK(pthread_create(&threads[i], NULL, queue_test_post, &producers[i]), 0);
    }
    while (finished < 3) {
        struct event *batch = event_loop_take(&loop, true);
        while (batch) {
            struct event *next = batch->next;
            int id = (int)(uintptr_t)batch->context;
            TEST_CHECK(batch->param1, counts[id]);
            if (batch->type == MENU_CLOSED) ++finished;
            else ++counts[id];
            free(batch);
            batch = next;
        }
    }
    for (int i = 0; i < 3; ++i) {
        pthread_join(threads[i], NULL);
        TEST_CHECK(counts[i], 20000);
    }
    TEST_CHECK(event_loop_take(&loop, false) == NULL, true);
    pthread_cond_destroy(&loop.ready);
    pthread_mutex_destroy(&loop.lock);
})
